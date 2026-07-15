"""
Convert the existing start-time dataset (train.jsonl / full dataset) into
per-machine job-sequencing records, deduplicating multiple records of the
same instance that collapse to the identical sequencing (different start
times / slack, same job order -- not useful to train on repeatedly).

Input record shape (existing dataset):
  {"instance": {..., "num_jobs", "num_machines", "durations", "machines"},
   "solution": {"starts": [[...]], "makespan": int, "optimal_makespan": int,
                "gap_percent": float, "is_optimal": bool},
   "solver_stats": {...}}

Output record shape (new, sequencing target):
  {"instance": {...same...},
   "solution": {"sequences": [[job_ids...] per machine], "makespan": int,
                "optimal_makespan": int, "gap_percent": float,
                "is_optimal": bool},
   "solver_stats": {...same...}}

Usage:
    python3 convert_to_sequences.py --input dataset.jsonl --output sequences.jsonl
"""

import json
import argparse
from collections import defaultdict


def extract_sequences(num_jobs, num_machines, machines, starts):
    """
    machines[j][t] = which machine job j's t-th task runs on (0-indexed).
    starts[j][t]   = solved start time of job j's t-th task.
    Returns: list of length num_machines, each a list of job indices
             (0-indexed) in the order they run on that machine.
    """
    per_machine = [[] for _ in range(num_machines)]
    for j in range(num_jobs):
        for t in range(num_machines):
            m = machines[j][t]
            per_machine[m].append((starts[j][t], j))
    sequences = []
    for m in range(num_machines):
        per_machine[m].sort(key=lambda pair: pair[0])
        sequences.append([job for _, job in per_machine[m]])
    return sequences


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    # Group raw records by instance id so dedup happens within an instance,
    # never across different instances.
    by_instance = defaultdict(list)
    total_input_records = 0
    malformed = 0

    with open(args.input) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total_input_records += 1
            try:
                rec = json.loads(line)
                inst_id = rec["instance"]["id"]
                by_instance[inst_id].append(rec)
            except (json.JSONDecodeError, KeyError):
                malformed += 1

    total_instances = len(by_instance)

    # Per-size stats accumulators
    size_stats = defaultdict(lambda: {
        "instances": 0, "input_records": 0, "output_records": 0,
        "duplicates_removed": 0
    })

    output_records = []
    total_duplicates_removed = 0

    for inst_id, recs in by_instance.items():
        nj = recs[0]["instance"]["num_jobs"]
        nm = recs[0]["instance"]["num_machines"]
        size_key = (nj, nm)
        size_stats[size_key]["instances"] += 1
        size_stats[size_key]["input_records"] += len(recs)

        best_by_sequence = {}  # signature -> chosen record (lowest makespan)

        for rec in recs:
            inst = rec["instance"]
            sol = rec["solution"]
            try:
                sequences = extract_sequences(
                    inst["num_jobs"], inst["num_machines"],
                    inst["machines"], sol["starts"]
                )
            except (KeyError, IndexError):
                malformed += 1
                continue

            key = tuple(tuple(seq) for seq in sequences)
            makespan = sol["makespan"]

            if key in best_by_sequence:
                if makespan < best_by_sequence[key][0]["solution"]["makespan"]:
                    best_by_sequence[key] = (rec, sequences)
                size_stats[size_key]["duplicates_removed"] += 1
                total_duplicates_removed += 1
                continue

            best_by_sequence[key] = (rec, sequences)

        for key, (rec, sequences) in best_by_sequence.items():
            out_rec = {
                "instance": rec["instance"],
                "solution": {
                    "sequences": sequences,
                    "makespan": rec["solution"]["makespan"],
                    "optimal_makespan": rec["solution"].get("optimal_makespan", -1),
                    "gap_percent": rec["solution"].get("gap_percent", -1.0),
                    "is_optimal": rec["solution"].get("is_optimal", False),
                },
                "solver_stats": rec.get("solver_stats", {}),
            }
            output_records.append(out_rec)
            size_stats[size_key]["output_records"] += 1

    with open(args.output, "w") as out_f:
        for rec in output_records:
            out_f.write(json.dumps(rec) + "\n")

    # ---- Stats report ----
    print("=" * 72)
    print("CONVERSION SUMMARY")
    print("=" * 72)
    print(f"Input records read:          {total_input_records}")
    print(f"Malformed/skipped records:   {malformed}")
    print(f"Unique instances:            {total_instances}")
    print(f"Total duplicate sequences removed: {total_duplicates_removed}")
    print(f"Output records written:      {len(output_records)}")
    print()
    print(f"{'size':<10}{'instances':<12}{'in_records':<12}{'out_records':<13}{'dupes_removed':<15}{'rec/inst':<10}")
    print("-" * 72)
    for (nj, nm) in sorted(size_stats.keys()):
        s = size_stats[(nj, nm)]
        rec_per_inst = round(s["output_records"] / s["instances"], 2) if s["instances"] else 0
        print(
            f"{nj}x{nm:<8}{s['instances']:<12}{s['input_records']:<12}"
            f"{s['output_records']:<13}{s['duplicates_removed']:<15}{rec_per_inst:<10}"
        )
    print("=" * 72)
    print(f"\nReduction: {total_input_records} -> {len(output_records)} records "
          f"({100*(1 - len(output_records)/max(1,total_input_records)):.1f}% removed as duplicate sequencings)")


if __name__ == "__main__":
    main()