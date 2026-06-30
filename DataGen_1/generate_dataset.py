"""
JSP Dataset Generator, cluster-ready version.

Designed to be called by a SLURM array job. Each invocation handles one
(nj, nm, dur_max) combination and runs MiniZinc instances in parallel
using a multiprocessing pool.

Usage:
    python generate_dataset.py \
        --nj 10 --nm 10 --dur-max 100 \
        --num-instances 500 \
        --workers 16 \
        --output /scratch/$USER/task_K.jsonl \
        --seed 42
"""

import os
import json
import random
import subprocess
import argparse
import tempfile
from multiprocessing import Pool

MODEL_PATH = "model.mzn"
TIMEOUT_MS = 900000  # 15 minutes per MiniZinc invocation


# Instance generation
def generate_random_instance(num_jobs, num_machines, duration_range, rng):
    """Generate one random JSP instance using the given Random object."""
    durations = []
    machines = []
    for _ in range(num_jobs):
        dur_row = [rng.randint(1, duration_range) for _ in range(num_machines)]
        mach_row = list(range(num_machines))
        rng.shuffle(mach_row)
        durations.append(dur_row)
        machines.append(mach_row)
    return {
        "n_jobs": num_jobs,
        "n_machines": num_machines,
        "job_task_duration": durations,
        "job_task_machine": machines
    }


# Single-instance pipeline (runs inside a worker process)
def run_single_instance(args):
    """
    Generate one instance, solve it with MiniZinc, return a list of JSONL
    record dicts (one per improving solution found). Returns an empty list
    on solver failure.

    args: (nj, nm, dur_max, instance_seed, global_id_str)
    """
    nj, nm, dur_max, instance_seed, global_id_str = args

    rng = random.Random(instance_seed)
    instance = generate_random_instance(nj, nm, dur_max, rng)

    # Each worker process writes to its own temp file to avoid collisions.
    fd, temp_json = tempfile.mkstemp(prefix=f"jsp_{os.getpid()}_", suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(instance, f)

        cmd = [
            "minizinc", "--solver", "Chuffed",
            "--all-solutions", "--statistics",
            "-t", str(TIMEOUT_MS),
            "--output-mode", "json", "--json-stream",
            MODEL_PATH, temp_json
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(
                f"[WARN] MiniZinc failed for {global_id_str} "
                f"(exit {result.returncode}): {result.stderr[:200]}",
                flush=True
            )
            return []

        
        # Parse the JSON-stream output
        solution_list = []
        final_status = "UNKNOWN"
        solver_stats = {}

        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry["type"] == "solution":
                    solution_list.append(entry["output"]["json"])
                elif entry["type"] == "status":
                    final_status = entry["status"]
                elif entry["type"] == "statistics":
                    solver_stats.update(entry["statistics"])
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        if not solution_list:
            return []

        solver_proved_optimality = (final_status == "OPTIMAL_SOLUTION")
        best_makespan_found = solution_list[-1]["C"]
        optimal_makespan = best_makespan_found if solver_proved_optimality else -1

        
        # Build one record per improving solution (training data density)
        records = []
        for i, sol in enumerate(solution_list):
            is_last = (i == len(solution_list) - 1)
            current_makespan = sol["C"]

            if solver_proved_optimality:
                gap_percent = ((current_makespan - optimal_makespan) * 100.0) / optimal_makespan
            else:
                gap_percent = -1.0

            record = {
                "instance": {
                    "source": "synthetic_generator",
                    "id": global_id_str,
                    "num_jobs": instance["n_jobs"],
                    "num_machines": instance["n_machines"],
                    "durations": instance["job_task_duration"],
                    "machines": instance["job_task_machine"]
                },
                "solution": {
                    "starts": sol["x"],
                    "makespan": current_makespan,
                    "optimal_makespan": optimal_makespan,
                    "gap_percent": round(gap_percent, 2),
                    "is_optimal": bool(is_last and solver_proved_optimality)
                },
                "solver_stats": {
                    # These are aggregate stats for the full solve, not per-solution.
                    "nodes": solver_stats.get("nodes", 0),
                    "failures": solver_stats.get("failures", 0),
                    "solve_time": solver_stats.get("solveTime", 0.0)
                }
            }
            records.append(record)

        return records

    finally:
        # Always remove the temp file, even if an exception occurred.
        if os.path.exists(temp_json):
            os.remove(temp_json)


# Main entry point
def parse_args():
    parser = argparse.ArgumentParser(description="JSP dataset generator (cluster-ready)")
    parser.add_argument("--nj",            type=int, required=True, help="Number of jobs")
    parser.add_argument("--nm",            type=int, required=True, help="Number of machines")
    parser.add_argument("--dur-max",       type=int, required=True, help="Max task duration")
    parser.add_argument("--num-instances", type=int, default=500,   help="Instances to generate")
    parser.add_argument("--workers",       type=int, default=8,     help="Parallel MiniZinc processes")
    parser.add_argument("--output",        type=str, required=True, help="Output JSONL file path")
    parser.add_argument("--seed",          type=int, default=0,     help="Base random seed")
    parser.add_argument("--task-id",       type=int, default=0,     help="SLURM array task ID (for unique instance IDs)")
    return parser.parse_args()


def main():
    args = parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    print(
        f"Starting: nj={args.nj} nm={args.nm} dur_max={args.dur_max} | "
        f"instances={args.num_instances} workers={args.workers} seed={args.seed}",
        flush=True
    )

    work_items = []
    for local_idx in range(args.num_instances):
        instance_seed = hash((args.seed, args.task_id, local_idx)) & 0xFFFFFFFF
        global_id = f"synth_t{args.task_id:03d}_{local_idx:05d}"
        work_items.append((args.nj, args.nm, args.dur_max, instance_seed, global_id))

    total_records = 0
    failed = 0

    with open(args.output, "w") as out_file:
        with Pool(processes=args.workers) as pool:
            for i, records in enumerate(
                pool.imap_unordered(run_single_instance, work_items)
            ):
                if not records:
                    failed += 1
                else:
                    for rec in records:
                        out_file.write(json.dumps(rec) + "\n")
                    total_records += len(records)

                if (i + 1) % 10 == 0 or (i + 1) == args.num_instances:
                    print(
                        f"  Progress: {i+1}/{args.num_instances} instances | "
                        f"{total_records} records written | {failed} failures",
                        flush=True
                    )

    print(
        f"Done. Total records: {total_records} | Failed instances: {failed}",
        flush=True
    )


if __name__ == "__main__":
    main()
