"""
solve_v2fixed_lds.py

Enriches v2fixed_eval_results.jsonl with, for every structurally valid line:
  - k                : smallest number of discrepancies needed for the solver
                       to accept the LLM's proposed sequencing (k=0 means the
                       proposal was directly cycle-free/feasible)
  - cycle_free        : True iff k == 0
  - lds_status        : "solved" | "k_cap_exceeded" | "timeout_undetermined"
  - makespan          : C at the k found (only set if solved)
  - gap_percent       : 100 * (makespan - best_makespan) / best_makespan
  - lds_solve_time_sec: total wall time spent searching over k for this instance

Structurally invalid lines are passed through unchanged, with these five
fields set to null, so the output file has the same number of lines as the
input and stays a drop-in superset.

Needs durations/machines, which are NOT in v2fixed_eval_results.jsonl -- these
are joined in from val_1950.jsonl by id.

Checkpointed: safe to resume after a crash or SLURM timeout.
"""

import json
import os
import time
import argparse
from datetime import timedelta

from minizinc import Instance, Model, Solver, Status

MZN_CODE = r"""
int: J;
int: M;
int: T = M;

set of int: Job = 1..J;
set of int: Task = 1..T;
set of int: Machine = 0..(M-1);

array[Job, Task] of int: durations;
array[Job, Task] of 0..(M-1): machines;
array[Job, Job, Machine] of bool: x;
int: k;

int: max_time = sum(durations);
var 0..max_time: C;
array[Job, Task] of var 0..max_time: S;
array[Job, Job, Machine] of var bool: X;

constraint forall(j in Job, t in Task)(durations[j, t] >= 0);
constraint forall(j in Job, t in 1..(T-1)) (S[j, t] + durations[j, t] <= S[j, t+1]);
constraint forall(j in Job)(0 <= S[j, 1]);

constraint forall(m in Machine, a, b in Job where a < b) (
    let {
        int: t_a = sum(t in Task where machines[a,t] == m)(t),
        int: t_b = sum(t in Task where machines[b,t] == m)(t)
    } in
    (X[a,b,m] -> (S[a, t_a] + durations[a, t_a] <= S[b, t_b]))
    /\
    (not(X[a,b,m]) -> (S[b, t_b] + durations[b, t_b] <= S[a, t_a]))
);

constraint sum(m in Machine, a, b in Job where a < b)(bool2int(X[a,b,m] != x[a,b,m])) <= k;
constraint forall(j in Job) (S[j, M] + durations[j, M] <= C);

solve minimize C;
"""


def build_model():
    chuffed = Solver.lookup("chuffed")
    jssp_model = Model()
    jssp_model.add_string(MZN_CODE)

    # smoke test, fail fast if the model doesn't compile on this node
    _smoke = Instance(chuffed, jssp_model)
    _smoke["J"] = 2
    _smoke["M"] = 2
    _smoke["durations"] = [[1, 1], [1, 1]]
    _smoke["machines"] = [[0, 1], [1, 0]]
    _smoke["x"] = [[[False, False], [False, False]], [[False, False], [False, False]]]
    _smoke["k"] = 2
    _res = _smoke.solve(timeout=timedelta(seconds=10))
    assert _res.status.has_solution(), "Model failed on trivial smoke instance -- check MZN_CODE."
    print("MiniZinc model compiles and solves. Smoke test OK.", flush=True)
    return chuffed, jssp_model


def precedences(num_jobs, num_machines, machines, sequences_matrix):
    """
    Builds the pairwise precedence indicator x[a][b][m] from the LLM's
    proposed per-machine sequences (0-indexed jobs), instead of from solved
    start times. sequences_matrix[m] is the row-th machine's job order.
    x[a][b][m] = True iff job a is scheduled before job b on machine m
    according to the LLM's proposal.
    """
    # position of each job within its machine's proposed row
    position_in_row = [[0] * num_machines for _ in range(num_jobs)]
    for m in range(num_machines):
        row = sequences_matrix[m]
        for pos, job in enumerate(row):
            position_in_row[job][m] = pos

    x = [[[False] * num_machines for _ in range(num_jobs)] for _ in range(num_jobs)]
    for m in range(num_machines):
        for a in range(num_jobs - 1):
            for b in range(a + 1, num_jobs):
                if position_in_row[a][m] < position_in_row[b][m]:
                    x[a][b][m] = True
    return x


def lds(chuffed, jssp_model, J, M, durations, machines, x, k_cap, per_solve_timeout_seconds):
    """
    Returns (status, k_found, makespan, elapsed_seconds)
    status in {"solved", "k_cap_exceeded", "timeout_undetermined"}
    """
    t_start = time.time()
    for k in range(k_cap + 1):
        instance = Instance(chuffed, jssp_model)
        instance["J"] = J
        instance["M"] = M
        instance["durations"] = durations
        instance["machines"] = machines
        instance["x"] = x
        instance["k"] = k

        response = instance.solve(timeout=timedelta(seconds=per_solve_timeout_seconds))

        if response.status.has_solution():
            makespan = getattr(response.solution, "C", None)
            if makespan is None:
                makespan = response.objective
            elapsed = time.time() - t_start
            return "solved", k, makespan, elapsed

        if response.status == Status.UNKNOWN:
            elapsed = time.time() - t_start
            return "timeout_undetermined", k, None, elapsed
        # else UNSATISFIABLE for this k -- move on to k+1

    elapsed = time.time() - t_start
    return "k_cap_exceeded", None, None, elapsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="/home/mazerouali/Desktop/fine_tuning_v3_backup/v3_evaluation/v3_eval_results.jsonl")
    parser.add_argument("--instances", default="/home/mazerouali/Desktop/val_1950.jsonl")
    parser.add_argument("--output", default="/home/mazerouali/Desktop/fine_tuning_v3_backup/v3_evaluation/v3_eval_results_solved.jsonl")
    parser.add_argument("--k_cap", type=int, default=50,
                         help="Max k to try per instance before giving up.")
    parser.add_argument("--per_solve_timeout", type=int, default=600,
                         help="Timeout in seconds for each individual k solve.")
    args = parser.parse_args()

    # load instance data (durations/machines) by id
    instances_by_id = {}
    with open(args.instances) as f:
        for line in f:
            rec = json.loads(line)
            instances_by_id[rec["id"]] = rec

    chuffed, jssp_model = build_model()

    done_ids = set()
    if os.path.exists(args.output):
        with open(args.output) as f:
            for line in f:
                try:
                    done_ids.add(json.loads(line)["id"])
                except Exception:
                    pass
    print(f"Resuming, {len(done_ids)} lines already written.", flush=True)

    n_processed = 0
    with open(args.input) as fin, open(args.output, "a") as fout:
        for line in fin:
            rec = json.loads(line)
            if rec["id"] in done_ids:
                continue

            if not rec.get("structural_validity"):
                rec["k"] = None
                rec["cycle_free"] = None
                rec["lds_status"] = None
                rec["makespan"] = None
                rec["gap_percent"] = None
                rec["lds_solve_time_sec"] = None
                fout.write(json.dumps(rec) + "\n")
                fout.flush()
                continue

            inst = instances_by_id.get(rec["id"])
            if inst is None:
                print(f"WARNING: {rec['id']} not found in {args.instances}, skipping.", flush=True)
                continue

            J = rec["num_jobs"]
            M = rec["num_machines"]
            durations = inst["durations"]
            machines = inst["machines"]
            sequences_matrix = rec["extracted_matrix"]

            x = precedences(J, M, machines, sequences_matrix)
            status, k, makespan, elapsed = lds(
                chuffed, jssp_model, J, M, durations, machines, x,
                args.k_cap, args.per_solve_timeout
            )

            rec["k"] = k
            rec["cycle_free"] = (k == 0) if status == "solved" else None
            rec["lds_status"] = status
            rec["makespan"] = makespan
            rec["gap_percent"] = (
                round(100 * (makespan - rec["best_makespan"]) / rec["best_makespan"], 3)
                if makespan is not None else None
            )
            rec["lds_solve_time_sec"] = round(elapsed, 2)

            fout.write(json.dumps(rec) + "\n")
            fout.flush()

            n_processed += 1
            print(f"{rec['id']} ({J}x{M}): status={status}, k={k}, "
                  f"makespan={makespan}, gap%={rec['gap_percent']}, "
                  f"{elapsed:.1f}s", flush=True)

    print(f"Done. Processed {n_processed} structurally valid lines this run.")


if __name__ == "__main__":
    main()