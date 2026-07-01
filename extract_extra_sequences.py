"""
Reprocess the raw 25M-record dataset (all intermediate solutions, no gap
filter applied) to extract additional sequencing records for large instances
that came out thin after the original 0-3% filter.

This does NOT re-run any solver. It reads the already-generated solution
records and applies a higher gap tolerance, extracting sequences the same
way convert_to_sequences.py does, then deduplicates by sequence signature.

The gap formula used throughout this project:
    gap = (current_makespan - optimal_makespan) / current_makespan * 100
(not the supervisor's ratio convention -- consistent with original filtering)

Reads:
    - sequences.jsonl (already-converted base dataset, used to detect which
      instance IDs already have enough coverage -- we only top-up thin sizes)
    - raw 25M-record JSONL (your original 52GB dataset before filtering)

Writes:
    - extra_sequences.jsonl (new unique sequences not already in sequences.jsonl)

Usage:
    python3 extract_extra_sequences.py \
        --existing sequences.jsonl \
        --raw /path/to/full_raw_dataset.jsonl \
        --output extra_sequences.jsonl \
        --gap-tolerance 10.0 \
        --target-sizes "15,12;15,15;20,15"
"""

import json
import argparse
from collections import defaultdict


def extract_sequences(num_jobs, num_machines, machines, starts):
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
    parser.add_argument("--existing",       required=True,
                        help="sequences.jsonl produced by convert_to_sequences.py")
    parser.add_argument("--raw",            required=True,
                        help="Full raw 25M-record JSONL (all solutions, no gap filter)")
    parser.add_argument("--output",         required=True)
    parser.add_argument("--gap-tolerance",  type=float, default=10.0,
                        help="Max gap%% to accept: (current-optimal)/current*100")
    parser.add_argument("--target-sizes",   type=str, default="15,12;15,15;20,15",
                        help="Size classes to top-up, e.g. '15,12;15,15;20,15'")
    args = parser.parse_args()

    target_sizes = set()
    for pair in args.target_sizes.split(";"):
        nj, nm = pair.strip().split(",")
        target_sizes.add((int(nj), int(nm)))
    print(f"Target sizes to top up: {target_sizes}")
    print(f"Gap tolerance: {args.gap_tolerance}%")

    # Load the sequence signatures already present in sequences.jsonl so we
    # don't re-add anything already covered (per-instance dedup)
    print("Loading existing sequences (to avoid re-adding already-covered records)...")
    existing_sigs = defaultdict(set)   # inst_id -> set of sequence signatures
    existing_counts = defaultdict(int)
    with open(args.existing) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            inst = rec["instance"]
            size = (inst["num_jobs"], inst["num_machines"])
            if size not in target_sizes:
                continue
            key = tuple(tuple(seq) for seq in rec["solution"]["sequences"])
            existing_sigs[inst["id"]].add(key)
            existing_counts[size] += 1

    print("Existing counts in target sizes:")
    for size in sorted(target_sizes):
        print(f"  {size[0]}x{size[1]}: {existing_counts[size]} records")

    # Stream through the raw dataset -- large file, don't load into memory
    print(f"\nStreaming raw dataset: {args.raw}")
    print("(This may take a while for a 52GB file -- progress printed every 1M lines)")

    new_by_instance = defaultdict(dict)  # inst_id -> sig -> best record
    lines_read = 0
    skipped_size = 0
    skipped_gap = 0
    skipped_no_optimal = 0
    accepted = 0

    with open(args.raw) as f:
        for line in f:
            lines_read += 1
            if lines_read % 1_000_000 == 0:
                print(f"  {lines_read:,} lines read | {accepted} new records so far")

            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                inst = rec["instance"]
                size = (inst["num_jobs"], inst["num_machines"])

                if size not in target_sizes:
                    skipped_size += 1
                    continue

                sol = rec["solution"]
                optimal = sol.get("optimal_makespan", -1)
                current = sol.get("makespan", 0)

                if optimal <= 0:
                    # No proven optimal available -- use gap_percent if stored,
                    # otherwise skip rather than accept unknown-quality records
                    gap_pct = sol.get("gap_percent", -1.0)
                    if gap_pct < 0:
                        skipped_no_optimal += 1
                        continue
                else:
                    if current <= 0:
                        skipped_no_optimal += 1
                        continue
                    gap_pct = ((current - optimal) / current) * 100.0

                if gap_pct > args.gap_tolerance:
                    skipped_gap += 1
                    continue

                sequences = extract_sequences(
                    inst["num_jobs"], inst["num_machines"],
                    inst["machines"], sol["starts"]
                )
                sig = tuple(tuple(seq) for seq in sequences)
                inst_id = inst["id"]

                # Skip if already in existing base dataset
                if sig in existing_sigs.get(inst_id, set()):
                    continue

                # Dedup within new candidates too, keep best makespan
                if sig in new_by_instance[inst_id]:
                    if current < new_by_instance[inst_id][sig]["solution"]["makespan"]:
                        new_by_instance[inst_id][sig] = rec
                        new_by_instance[inst_id][sig]["solution"]["sequences"] = sequences
                else:
                    rec_out = dict(rec)
                    rec_out["solution"] = dict(sol)
                    rec_out["solution"]["sequences"] = sequences
                    new_by_instance[inst_id][sig] = rec_out
                    accepted += 1

            except (json.JSONDecodeError, KeyError, IndexError):
                continue

    print(f"\nFinished streaming {lines_read:,} lines")
    print(f"  Skipped (wrong size):      {skipped_size:,}")
    print(f"  Skipped (gap too high):    {skipped_gap:,}")
    print(f"  Skipped (no optimal):      {skipped_no_optimal:,}")
    print(f"  New unique sequences found: {accepted:,}")

    written = 0
    new_counts = defaultdict(int)
    with open(args.output, "w") as out_f:
        for inst_id, sigs in new_by_instance.items():
            for sig, rec in sigs.items():
                # Build clean output record matching sequences.jsonl format
                out_rec = {
                    "instance": rec["instance"],
                    "solution": {
                        "sequences": rec["solution"]["sequences"],
                        "makespan": rec["solution"]["makespan"],
                        "optimal_makespan": rec["solution"].get("optimal_makespan", -1),
                        "gap_percent": round(rec["solution"].get("gap_percent", -1.0), 2),
                        "is_optimal": rec["solution"].get("is_optimal", False),
                    },
                    "solver_stats": rec.get("solver_stats", {}),
                }
                out_f.write(json.dumps(out_rec) + "\n")
                written += 1
                size = (rec["instance"]["num_jobs"], rec["instance"]["num_machines"])
                new_counts[size] += 1

    print(f"\nNew records written to {args.output}: {written}")
    print("Breakdown by size:")
    for size in sorted(new_counts):
        print(f"  {size[0]}x{size[1]}: {new_counts[size]} new records "
              f"(was {existing_counts[size]}, now {existing_counts[size] + new_counts[size]})")
    print(
        "\nNext step: cat sequences.jsonl extra_sequences.jsonl > sequences_augmented.jsonl"
        "\nthen re-run build_finetune_jsonl.py on sequences_augmented.jsonl"
    )


if __name__ == "__main__":
    main()