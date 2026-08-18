"""
retry_v2fixed_timeouts.py

Targets only the lines in an already-produced *_solved.jsonl file whose
lds_status is "timeout_undetermined", and retries them with a larger
per_solve_timeout. Resumes the k-search from the k value it had already
reached (NOT from k=0), since all k' < k were already proven UNSAT in the
first pass and don't need to be re-solved -- only the k it stalled on, and
any further k above it if that one is still inconclusive.

Rewrites the output file in place after every processed instance, so
progress is preserved line-by-line: rerunning this script simply picks up
whatever is still "timeout_undetermined" and leaves already-resolved lines
untouched. Total lds_solve_time_sec is accumulated across passes (old time
+ this retry's time), not overwritten, so the reported solve time reflects
total effort spent, not just the final successful attempt.

Usage:
    python retry_v2fixed_timeouts.py \
        --output v2fixed_eval_results_solved.jsonl \
        --instances val_1950.jsonl \
        --per_solve_timeout 90 \
        --k_cap 50
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


def precedences(num_jobs, num_machines, sequences_matrix):
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


def lds_resume(chuffed, jssp_model, J, M, durations, machines, x,
                start_k, k_cap, per_solve_timeout_seconds):
    """
    Same as the original lds(), but starts the search at start_k instead of
    0, since all k < start_k were already proven UNSAT in a previous pass.
    Returns (status, k_found, makespan, elapsed_seconds).
    """
    t_start = time.time()
    for k in range(start_k, k_cap + 1):
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


def write_all(records, path):
    """Rewrite the whole file, preserving original line order."""
    tmp_path = path + ".tmp"
    with open(tmp_path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    os.replace(tmp_path, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="v2fixed_eval_results_solved.jsonl",
                         help="File to update in place.")
    parser.add_argument("--instances", default="val_1950.jsonl")
    parser.add_argument("--k_cap", type=int, default=50)
    parser.add_argument("--per_solve_timeout", type=int, default=600,
                         help="Larger timeout per k for this retry pass.")
    args = parser.parse_args()

    instances_by_id = {}
    with open(args.instances) as f:
        for line in f:
            rec = json.loads(line)
            instances_by_id[rec["id"]] = rec

    with open(args.output) as f:
        records = [json.loads(line) for line in f]

    target_indices = [i for i, r in enumerate(records) if r.get("lds_status") == "timeout_undetermined"]
    print(f"Found {len(target_indices)} timeout_undetermined lines to retry.", flush=True)
    if not target_indices:
        print("Nothing to do.")
        return

    chuffed, jssp_model = build_model()

    for count, idx in enumerate(target_indices, 1):
        rec = records[idx]
        inst = instances_by_id.get(rec["id"])
        if inst is None:
            print(f"WARNING: {rec['id']} not found in {args.instances}, skipping.", flush=True)
            continue

        J = rec["num_jobs"]
        M = rec["num_machines"]
        durations = inst["durations"]
        machines = inst["machines"]
        sequences_matrix = rec["extracted_matrix"]

        start_k = rec["k"]  # resume at the k it stalled on, not 0
        prior_time = rec.get("lds_solve_time_sec") or 0.0

        x = precedences(J, M, sequences_matrix)
        status, k, makespan, elapsed = lds_resume(
            chuffed, jssp_model, J, M, durations, machines, x,
            start_k, args.k_cap, args.per_solve_timeout
        )

        rec["k"] = k
        rec["cycle_free"] = (k == 0) if status == "solved" else None
        rec["lds_status"] = status
        rec["makespan"] = makespan
        rec["gap_percent"] = (
            round(100 * (makespan - rec["best_makespan"]) / rec["best_makespan"], 3)
            if makespan is not None else None
        )
        rec["lds_solve_time_sec"] = round(prior_time + elapsed, 2)

        records[idx] = rec
        write_all(records, args.output)  # checkpoint after every instance

        print(f"[{count}/{len(target_indices)}] {rec['id']} ({J}x{M}): "
              f"status={status}, k={k}, makespan={makespan}, "
              f"gap%={rec['gap_percent']}, retry_elapsed={elapsed:.1f}s, "
              f"total_time={rec['lds_solve_time_sec']}s", flush=True)

    still_timeout = sum(1 for r in records if r.get("lds_status") == "timeout_undetermined")
    print(f"Done. {still_timeout} lines still timeout_undetermined after this pass "
          f"(rerun the script again with a larger --per_solve_timeout if needed).")


if __name__ == "__main__":
    main()
