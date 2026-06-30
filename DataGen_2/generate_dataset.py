"""
JSP Dataset Generator v2 -- two-phase algorithm, sequencing targets.

Phase 1: solve to minimize C under a timeout, no solution streaming
         (cheap -- avoids the I/O cost of writing every intermediate
         solution, which was the original bottleneck).
Phase 2: re-solve as a satisfaction problem with C bounded to
         [i_o, i_o / (1 - GAP_TOLERANCE)], enumerating solutions with
         --all-solutions, capped at MAX_SOLUTIONS_PER_INSTANCE so a
         loosely-constrained instance can't enumerate forever.

Output records store PER-MACHINE JOB SEQUENCES (not raw start times),
derived from each solution's start-time matrix by sorting each
machine's assigned tasks by their solved start time.

Usage (per SLURM array task -- one (nj, nm, dur_max) combo):
    python generate_dataset.py \
        --nj 15 --nm 15 --dur-max 100 \
        --num-instances 300 \
        --workers 16 \
        --output /scratch/$USER/task_K.jsonl \
        --seed 42 --task-id 7
"""

import os
import json
import random
import subprocess
import argparse
import tempfile
import time
from multiprocessing import Pool

PHASE1_MODEL = "model_phase1.mzn"
PHASE2_MODEL = "model_phase2.mzn"

GAP_TOLERANCE = 0.03            # (current - optimal) / current <= 3%, matches original dataset
MAX_SOLUTIONS_PER_INSTANCE = 25 # hard cap on phase-2 enumeration, per instance

# Phase-1 timeouts scale with instance size: small instances solve to
# true optimality in seconds, larger ones need real budget to get close.
# Keyed by (n_jobs, n_machines) -- extend if you add more sizes.
# Shorter than before -- we no longer need near-optimal proof, just a
# decent anchor for the 3% satisfaction band. This also buys back time
# to run more instances within the same wall-clock budget.
PHASE1_TIMEOUT_MS = {
    (3, 3): 3_000, (4, 4): 3_000, (5, 5): 5_000, (6, 6): 8_000,
    (8, 6): 15_000, (8, 8): 15_000, (10, 8): 30_000, (10, 10): 30_000,
    (12, 10): 60_000, (12, 12): 90_000, (15, 12): 120_000,
    (15, 15): 180_000, (20, 15): 240_000, (20, 20): 300_000,
}
PHASE2_TIMEOUT_MS = 300_000  # 5 min cap on the enumeration pass itself


def phase1_timeout_for(nj, nm):
    return PHASE1_TIMEOUT_MS.get((nj, nm), 900_000)  # fallback: 15 min


# Instance generation
def generate_random_instance(num_jobs, num_machines, duration_range, rng):
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


# Sequence extraction: convert a start-time matrix into per-machine job order
def extract_sequences(num_jobs, num_machines, job_task_machine, x):
    """
    x: solved start-time matrix, x[job][task_index] (0-indexed in Python,
       matches MiniZinc's 1-indexed array after JSON round-trip).
    Returns: list of length num_machines, each entry a list of job indices
             (0-indexed) in the order they run on that machine.
    """
    per_machine = [[] for _ in range(num_machines)]
    for j in range(num_jobs):
        for t in range(num_machines):
            m = job_task_machine[j][t]
            start_time = x[j][t]
            per_machine[m].append((start_time, j))
    sequences = []
    for m in range(num_machines):
        per_machine[m].sort(key=lambda pair: pair[0])
        sequences.append([job for _, job in per_machine[m]])
    return sequences


def write_dzn(path, params):
    with open(path, "w") as f:
        for key, val in params.items():
            f.write(f"{key} = {json.dumps(val)};\n")


def run_phase1(nj, nm, instance, timeout_ms):
    """Returns (i_o, status) -- i_o is best makespan found (None on total
    failure), status is the final MiniZinc status string (lets us tell
    'proved optimal' apart from 'timed out with best-found')."""
    fd, dzn_path = tempfile.mkstemp(prefix=f"p1_{os.getpid()}_", suffix=".dzn")
    try:
        os.close(fd)
        write_dzn(dzn_path, {
            "n_jobs": instance["n_jobs"],
            "n_machines": instance["n_machines"],
            "job_task_duration": instance["job_task_duration"],
            "job_task_machine": instance["job_task_machine"],
        })
        cmd = [
            "minizinc", "--solver", "Chuffed",
            "--statistics", "-t", str(timeout_ms),
            "--output-mode", "json", "--json-stream",
            PHASE1_MODEL, dzn_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        best_c = None
        status = "UNKNOWN"
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry.get("type") == "solution":
                    best_c = entry["output"]["json"]["C"]
                elif entry.get("type") == "status":
                    status = entry["status"]
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
        return best_c, status
    finally:
        if os.path.exists(dzn_path):
            os.remove(dzn_path)


def run_phase2(nj, nm, instance, i_o, timeout_ms, max_solutions):
    """
    Streams solutions from phase 2, stopping early once max_solutions is
    reached (kills the subprocess rather than waiting for it to exit).
    Returns a list of raw solution dicts (each containing 'x' and 'C').
    """
    c_ub = int(i_o / (1 - GAP_TOLERANCE))
    fd, dzn_path = tempfile.mkstemp(prefix=f"p2_{os.getpid()}_", suffix=".dzn")
    try:
        os.close(fd)
        write_dzn(dzn_path, {
            "n_jobs": instance["n_jobs"],
            "n_machines": instance["n_machines"],
            "job_task_duration": instance["job_task_duration"],
            "job_task_machine": instance["job_task_machine"],
            "C_lb": i_o,
            "C_ub": c_ub,
        })
        cmd = [
            "minizinc", "--solver", "Chuffed",
            "--all-solutions", "--statistics",
            "-t", str(timeout_ms),
            "--output-mode", "json", "--json-stream",
            PHASE2_MODEL, dzn_path
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        solutions = []
        start_time = time.time()
        deadline = start_time + (timeout_ms / 1000.0) + 5  # small grace margin

        for line in proc.stdout:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if entry.get("type") == "solution":
                    solutions.append(entry["output"]["json"])
                    if len(solutions) >= max_solutions:
                        break
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
            if time.time() > deadline:
                break

        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

        return solutions
    finally:
        if os.path.exists(dzn_path):
            os.remove(dzn_path)


# Single-instance pipeline (runs inside a worker process)
def run_single_instance(args):
    nj, nm, dur_max, instance_seed, global_id_str = args
    rng = random.Random(instance_seed)
    instance = generate_random_instance(nj, nm, dur_max, rng)

    stats = {
        "phase1_no_solution": 0, "phase1_timed_out": 0,
        "phase2_no_solution": 0, "raw_solutions": 0,
        "duplicate_sequences_skipped": 0, "records_written": 0,
    }

    timeout1 = phase1_timeout_for(nj, nm)
    i_o, p1_status = run_phase1(nj, nm, instance, timeout1)
    if i_o is None:
        print(f"[WARN] Phase 1 found no solution for {global_id_str}", flush=True)
        stats["phase1_no_solution"] = 1
        return [], stats
    if p1_status not in ("OPTIMAL_SOLUTION",):
        stats["phase1_timed_out"] = 1  # best-found, not proven -- expected/fine, just tracked

    raw_solutions = run_phase2(nj, nm, instance, i_o, PHASE2_TIMEOUT_MS, MAX_SOLUTIONS_PER_INSTANCE)
    stats["raw_solutions"] = len(raw_solutions)
    if not raw_solutions:
        print(f"[WARN] Phase 2 found no solutions for {global_id_str} (i_o={i_o})", flush=True)
        stats["phase2_no_solution"] = 1
        return [], stats

    # Deduplicate by sequencing signature: many enumerated solutions can
    # share identical per-machine job order with only slack/start-time
    # differences. Keep the lowest-makespan record per unique sequencing.
    best_by_sequence = {}
    for sol in raw_solutions:
        current_makespan = sol["C"]
        x = sol["x"]
        sequences = extract_sequences(nj, nm, instance["job_task_machine"], x)
        key = tuple(tuple(seq) for seq in sequences)

        if key in best_by_sequence and best_by_sequence[key]["makespan"] <= current_makespan:
            stats["duplicate_sequences_skipped"] += 1
            continue
        if key in best_by_sequence:
            stats["duplicate_sequences_skipped"] += 1

        best_by_sequence[key] = {"sequences": sequences, "makespan": current_makespan}

    records = []
    for entry in best_by_sequence.values():
        current_makespan = entry["makespan"]
        sequences = entry["sequences"]
        gap_percent = ((current_makespan - i_o) * 100.0) / current_makespan if current_makespan > 0 else 0.0

        record = {
            "instance": {
                "source": "synthetic_generator_v2",
                "id": global_id_str,
                "num_jobs": instance["n_jobs"],
                "num_machines": instance["n_machines"],
                "durations": instance["job_task_duration"],
                "machines": instance["job_task_machine"]
            },
            "solution": {
                "sequences": sequences,
                "makespan": current_makespan,
                "best_found_makespan": i_o,
                "gap_percent": round(gap_percent, 2),
                "is_best_found": bool(current_makespan == i_o)
            },
            "solver_stats": {
                "phase1_timeout_ms": timeout1,
                "phase1_proved_optimal": bool(p1_status == "OPTIMAL_SOLUTION"),
                "phase2_timeout_ms": PHASE2_TIMEOUT_MS
            }
        }
        records.append(record)

    stats["records_written"] = len(records)
    return records, stats


# Main entry point
def parse_args():
    parser = argparse.ArgumentParser(description="JSP dataset generator v2 (two-phase, sequencing targets)")
    parser.add_argument("--nj", type=int, required=True)
    parser.add_argument("--nm", type=int, required=True)
    parser.add_argument("--dur-max", type=int, required=True)
    parser.add_argument("--num-instances", type=int, default=200)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--output", type=str, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--task-id", type=int, default=0)
    return parser.parse_args()


def main():
    args = parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    print(
        f"Starting: nj={args.nj} nm={args.nm} dur_max={args.dur_max} | "
        f"instances={args.num_instances} workers={args.workers} seed={args.seed} | "
        f"phase1_timeout={phase1_timeout_for(args.nj, args.nm)}ms",
        flush=True
    )

    work_items = []
    for local_idx in range(args.num_instances):
        instance_seed = hash((args.seed, args.task_id, local_idx)) & 0xFFFFFFFF
        global_id = f"synth_t{args.task_id:03d}_{local_idx:05d}"
        work_items.append((args.nj, args.nm, args.dur_max, instance_seed, global_id))

    total_records = 0
    failed = 0
    agg = {
        "phase1_no_solution": 0, "phase1_timed_out": 0,
        "phase2_no_solution": 0, "raw_solutions": 0,
        "duplicate_sequences_skipped": 0,
    }

    with open(args.output, "w") as out_file:
        with Pool(processes=args.workers) as pool:
            for i, (records, stats) in enumerate(pool.imap_unordered(run_single_instance, work_items)):
                if not records:
                    failed += 1
                else:
                    for rec in records:
                        out_file.write(json.dumps(rec) + "\n")
                    total_records += len(records)

                for k in agg:
                    agg[k] += stats.get(k, 0)

                if (i + 1) % 10 == 0 or (i + 1) == args.num_instances:
                    print(
                        f"  Progress: {i+1}/{args.num_instances} instances | "
                        f"{total_records} records written | {failed} failures",
                        flush=True
                    )

    summary = {
        "task_id": args.task_id, "nj": args.nj, "nm": args.nm, "dur_max": args.dur_max,
        "num_instances_requested": args.num_instances,
        "instances_failed_entirely": failed,
        "records_written": total_records,
        "records_per_instance": round(total_records / max(1, args.num_instances - failed), 2),
        **agg,
    }
    stats_path = args.output + ".stats.json"
    with open(stats_path, "w") as sf:
        json.dump(summary, sf, indent=2)

    print(f"Done. Total records: {total_records} | Failed instances: {failed}", flush=True)
    print(f"Stats written to {stats_path}", flush=True)


if __name__ == "__main__":
    main()