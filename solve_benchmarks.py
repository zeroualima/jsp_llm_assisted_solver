"""
Solve benchmark instances using phase1 (minimize makespan) and record:
  - best makespan found within timeout
  - gap% vs BKS (best known solution from JSPLib)
  - per-machine job sequences derived from the solution
  - whether optimality was proved

Usage (local test):
    python3 solve_benchmarks.py \
        --index benchmarks/index.json \
        --output benchmarks/results_test.jsonl \
        --family ta --solver cpsat --timeout 60

Usage (SLURM array, one family per task -- see submit_benchmarks.sh):
    python3 solve_benchmarks.py \
        --index benchmarks/index.json \
        --output benchmarks/results_ta.jsonl \
        --family ta --solver cpsat --timeout 32400
"""

import json
import os
import argparse
import subprocess
import tempfile
import time
from collections import defaultdict

PHASE1_MODEL = "model_phase1.mzn"

SOLVER_MAP = {
    "cpsat":   "cp-sat",
    "chuffed": "org.chuffed.chuffed",
}

CPSAT_THREADS = 16  # matches --cpus-per-task in the SLURM script


def extract_sequences(num_jobs, num_machines, machines, x_raw):
    """
    Convert MiniZinc start-time array to per-machine job sequences.

    MiniZinc JSON output for array[1..J, 1..M] can be either:
      - nested:  [[s00, s01, ...], [s10, ...], ...]   (recent MiniZinc)
      - flat:    [s00, s01, ..., s(J-1)(M-1)]         (older output)

    Both are handled here.
    """
    # Normalise to nested list
    if x_raw and isinstance(x_raw[0], list):
        starts = x_raw  # already nested
    else:
        # flat -- reshape to J x M
        starts = [
            x_raw[j * num_machines:(j + 1) * num_machines]
            for j in range(num_jobs)
        ]

    per_machine = [[] for _ in range(num_machines)]
    for j in range(num_jobs):
        for t in range(num_machines):
            m = machines[j][t]
            per_machine[m].append((starts[j][t], j))

    sequences = []
    for m in range(num_machines):
        per_machine[m].sort(key=lambda p: p[0])
        sequences.append([job for _, job in per_machine[m]])
    return sequences


def write_dzn(path, instance):
    with open(path, "w") as f:
        f.write(f"n_jobs = {instance['num_jobs']};\n")
        f.write(f"n_machines = {instance['num_machines']};\n")
        f.write(f"job_task_duration = {json.dumps(instance['durations'])};\n")
        f.write(f"job_task_machine = {json.dumps(instance['machines'])};\n")


def solve_phase1(instance, solver_id, timeout_s, threads, minizinc_bin="minizinc"):
    timeout_ms = int(timeout_s * 1000)
    fd, dzn_path = tempfile.mkstemp(suffix=".dzn")
    try:
        os.close(fd)
        write_dzn(dzn_path, instance)

        cmd = [
            minizinc_bin, "--solver", solver_id,
            "--statistics",
            "-t", str(timeout_ms),
            "--output-mode", "json", "--json-stream",
            PHASE1_MODEL, dzn_path,
        ]

        # CP-SAT parallel threads flag
        if threads > 0 and solver_id == "cp-sat":
            cmd += ["-p", str(threads)]

        t0 = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True)
        elapsed = time.time() - t0

        if result.returncode not in (0, 1) and not result.stdout.strip():
            # Non-zero exit with no output usually means MiniZinc itself failed
            print(f"\n  [ERROR] MiniZinc exited {result.returncode}: "
                  f"{result.stderr[:300]}")
            return {"best_makespan": None, "status": "ERROR",
                    "solve_time_s": round(elapsed, 2), "sequences": None}

        best_makespan = None
        best_solution = None
        status = "UNKNOWN"

        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                etype = entry.get("type")
                if etype == "solution":
                    sol = entry["output"]["json"]
                    c = sol["C"]
                    if best_makespan is None or c < best_makespan:
                        best_makespan = c
                        best_solution = sol
                elif etype == "status":
                    status = entry["status"]
            except (json.JSONDecodeError, KeyError):
                continue

        sequences = None
        if best_solution is not None:
            x_raw = best_solution.get("x")
            if x_raw is None:
                print(f"\n  [WARN] 'x' key missing from solution JSON. "
                      f"Keys present: {list(best_solution.keys())}")
            else:
                try:
                    sequences = extract_sequences(
                        instance["num_jobs"], instance["num_machines"],
                        instance["machines"], x_raw
                    )
                except Exception as e:
                    print(f"\n  [WARN] extract_sequences failed: {e} "
                          f"| x_raw type={type(x_raw)}, "
                          f"len={len(x_raw) if hasattr(x_raw,'__len__') else '?'}")

        return {
            "best_makespan": best_makespan,
            "status": status,
            "solve_time_s": round(elapsed, 2),
            "sequences": sequences,
        }
    finally:
        if os.path.exists(dzn_path):
            os.remove(dzn_path)


def gap_vs_bks(makespan, bks):
    if bks <= 0 or makespan is None:
        return -1.0
    return round((makespan - bks) / makespan * 100.0, 2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index",    required=True)
    parser.add_argument("--output",   required=True)
    parser.add_argument("--family",   default=None)
    parser.add_argument("--difficulty", nargs="+", default=None)
    parser.add_argument("--solver",   default="cpsat",
                        choices=list(SOLVER_MAP.keys()))
    parser.add_argument("--timeout",  type=int, default=32400,
                        help="Timeout per instance in seconds (default 32400 = 9h)")
    parser.add_argument("--threads",  type=int, default=CPSAT_THREADS)
    args = parser.parse_args()

    # Resolve minizinc binary -- use explicit path if not on system PATH
    minizinc_bin = "minizinc"
    home = os.path.expanduser("~")
    local_mzn = os.path.join(home, "minizinc", "bin", "minizinc")
    if os.path.isfile(local_mzn):
        minizinc_bin = local_mzn
        print(f"Using local MiniZinc: {minizinc_bin}")

    # Check solver availability
    check = subprocess.run([minizinc_bin, "--solvers"],
                           capture_output=True, text=True)
    solver_id = SOLVER_MAP[args.solver]

    # Use hyphen-aware check: "cp-sat" not "cpsat"
    if solver_id not in check.stdout:
        print(f"WARNING: '{solver_id}' not found in --solvers output.")
        print(check.stdout)
        if args.solver == "cpsat":
            print("Falling back to Chuffed.")
            solver_id = SOLVER_MAP["chuffed"]
        else:
            raise RuntimeError(f"Solver '{solver_id}' unavailable.")
    else:
        print(f"Solver confirmed available: {solver_id}")

    with open(args.index) as f:
        index = json.load(f)

    if args.family:
        index = [e for e in index if e["family"] == args.family]
    if args.difficulty:
        index = [e for e in index if e.get("difficulty", "") in args.difficulty]

    print(f"Solving {len(index)} instances | solver={solver_id} | "
          f"timeout={args.timeout}s ({args.timeout/3600:.1f}h) | "
          f"threads={args.threads}")

    stats = defaultdict(lambda: {"solved": 0, "proved": 0, "failed": 0,
                                 "seq_null": 0, "gap_sum": 0.0, "gap_count": 0})
    written = 0

    with open(args.output, "w") as out_f:
        for i, meta in enumerate(index):
            name     = meta["name"]
            family   = meta["family"]
            bks      = meta.get("bks", -1)
            inst_path = meta["path"]

            with open(inst_path) as f:
                instance = json.load(f)

            print(f"[{i+1}/{len(index)}] {name} "
                  f"({instance['num_jobs']}x{instance['num_machines']}, "
                  f"{meta.get('difficulty','?')}, BKS={bks})...",
                  end=" ", flush=True)

            res = solve_phase1(instance, solver_id, args.timeout,
                               args.threads, minizinc_bin)
            gap = gap_vs_bks(res["best_makespan"], bks)

            print(f"makespan={res['best_makespan']} gap={gap}% "
                  f"status={res['status']} time={res['solve_time_s']}s "
                  f"seq={'OK' if res['sequences'] else 'NULL'}")

            record = {
                "instance_name": name,
                "family": family,
                "difficulty": meta.get("difficulty", "unknown"),
                "num_jobs": instance["num_jobs"],
                "num_machines": instance["num_machines"],
                "bks": bks,
                "best_makespan_found": res["best_makespan"],
                "gap_vs_bks_percent": gap,
                "status": res["status"],
                "proved_optimal": res["status"] == "OPTIMAL_SOLUTION",
                "solve_time_s": res["solve_time_s"],
                "solver": solver_id,
                "timeout_s": args.timeout,
                "sequences": res["sequences"],
            }
            out_f.write(json.dumps(record) + "\n")
            written += 1

            s = stats[family]
            if res["best_makespan"] is not None:
                s["solved"] += 1
                if res["status"] == "OPTIMAL_SOLUTION":
                    s["proved"] += 1
                if gap >= 0:
                    s["gap_sum"] += gap
                    s["gap_count"] += 1
            else:
                s["failed"] += 1
            if res["sequences"] is None:
                s["seq_null"] += 1

    print(f"\nWritten {written} records to {args.output}")
    print()
    print(f"{'family':<8}{'solved':<8}{'proved':<8}{'failed':<8}"
          f"{'seq_null':<10}{'avg_gap%':<10}")
    for fam in sorted(stats):
        s = stats[fam]
        avg = round(s["gap_sum"] / s["gap_count"], 2) if s["gap_count"] else -1
        print(f"{fam:<8}{s['solved']:<8}{s['proved']:<8}{s['failed']:<8}"
              f"{s['seq_null']:<10}{avg:<10}")


if __name__ == "__main__":
    main()
