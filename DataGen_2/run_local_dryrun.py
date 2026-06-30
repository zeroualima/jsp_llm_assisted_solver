"""
Local dry-run driver -- no SLURM, no array indexing.

Runs generate_dataset.py directly for a small slice of combos (mirrors
the cluster dry run: one small size + one target size, all 3 durations),
sequentially, on your own machine (i7 desktop or Colab CPU runtime).

Requires: minizinc binary on PATH with chuffed available, and
generate_dataset.py / model_phase1.mzn / model_phase2.mzn in this directory.

Usage:
    python3 run_local_dryrun.py
"""

import subprocess
import json
import os

# Mirrors the cluster dry-run slice: (3,3) as a fast small-size sanity
# check, (20,15) as a target-tier size to see real dedup/yield behavior.
DRY_RUN_COMBOS = [
    # (nj, nm, dur_max, num_instances)
    (3, 3, 10, 50),
    (3, 3, 50, 50),
    (3, 3, 100, 50),
    (20, 15, 10, 50),
    (20, 15, 50, 50),
    (20, 15, 100, 50),
]

OUTPUT_DIR = "./dryrun_parts"
WORKERS = 4  # adjust to your machine's core count (leave 1-2 cores free)


def run_combo(nj, nm, dur_max, num_instances, task_id):
    out_path = os.path.join(OUTPUT_DIR, f"dryrun_t{task_id}.jsonl")
    cmd = [
        "python3", "generate_dataset.py",
        "--nj", str(nj), "--nm", str(nm), "--dur-max", str(dur_max),
        "--num-instances", str(num_instances),
        "--workers", str(WORKERS),
        "--output", out_path,
        "--seed", "12345",
        "--task-id", str(task_id),
    ]
    print(f"\n=== Running nj={nj} nm={nm} dur_max={dur_max} ({num_instances} instances) ===")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"[WARN] task {task_id} (nj={nj}, nm={nm}, dur_max={dur_max}) exited with code {result.returncode}")
    return out_path


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    summaries = []
    for task_id, (nj, nm, dur_max, num_instances) in enumerate(DRY_RUN_COMBOS):
        out_path = run_combo(nj, nm, dur_max, num_instances, task_id)
        stats_path = out_path + ".stats.json"
        if os.path.exists(stats_path):
            with open(stats_path) as f:
                summaries.append(json.load(f))
        else:
            print(f"[WARN] no stats file produced for task {task_id} -- check the run for errors above")

    print("\n" + "=" * 70)
    print(f"{'size':<10}{'dur_max':<10}{'records':<10}{'rec/inst':<10}{'dupes':<10}{'failed':<10}")
    print("=" * 70)
    for s in summaries:
        print(
            f"{s['nj']}x{s['nm']:<7}{s['dur_max']:<10}{s['records_written']:<10}"
            f"{s['records_per_instance']:<10}{s['duplicate_sequences_skipped']:<10}"
            f"{s['instances_failed_entirely']:<10}"
        )

    total_records = sum(s["records_written"] for s in summaries)
    print("=" * 70)
    print(f"Total records across dry-run slice: {total_records}")
    print(
        "\nUse this records-per-instance figure to sanity-check the full-array "
        "estimate before submitting all 42 tasks (locally or via SLURM)."
    )


if __name__ == "__main__":
    main()