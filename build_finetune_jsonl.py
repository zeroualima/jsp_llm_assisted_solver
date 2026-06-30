"""
Build train_ft.jsonl / val_ft.jsonl (the 'text' field SFTTrainer expects)
from sequences.jsonl, splitting by instance id (90/10, no leakage) and
oversampling target sizes that came out thin after dedup.

Usage:
    python3 build_finetune_jsonl.py --input sequences.jsonl \
        --train-out train_ft.jsonl --val-out val_ft.jsonl
"""

import json
import argparse
import random
from collections import defaultdict

# Sizes that came out thin after dedup (per your conversion stats) and are
# benchmark-relevant -- duplicated this many extra times in the TRAIN split
# only (never touch val -- oversampling val would distort your eval numbers).
OVERSAMPLE_WEIGHTS = {
    (12, 10): 2, (12, 12): 2,
    (15, 12): 3, (15, 15): 4, (20, 15): 5,
}
DEFAULT_WEIGHT = 1
VAL_FRACTION = 0.10
SEED = 42


def build_text(rec):
    prompt_obj = {
        "num_jobs": rec["instance"]["num_jobs"],
        "num_machines": rec["instance"]["num_machines"],
        "durations": rec["instance"]["durations"],
        "machines": rec["instance"]["machines"],
    }
    completion_obj = {"sequences": rec["solution"]["sequences"]}
    return f"<prompt>{json.dumps(prompt_obj)}</prompt><completion>{json.dumps(completion_obj)}</completion>"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--train-out", required=True)
    parser.add_argument("--val-out", required=True)
    args = parser.parse_args()

    rng = random.Random(SEED)

    by_instance = defaultdict(list)
    with open(args.input) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            by_instance[rec["instance"]["id"]].append(rec)

    instance_ids = list(by_instance.keys())
    rng.shuffle(instance_ids)
    n_val = int(len(instance_ids) * VAL_FRACTION)
    val_ids = set(instance_ids[:n_val])
    train_ids = set(instance_ids[n_val:])

    train_lines = []
    val_lines = []
    size_train_counts = defaultdict(int)
    size_val_counts = defaultdict(int)

    for inst_id, recs in by_instance.items():
        is_val = inst_id in val_ids
        for rec in recs:
            nj, nm = rec["instance"]["num_jobs"], rec["instance"]["num_machines"]
            text = build_text(rec)
            if is_val:
                val_lines.append(text)
                size_val_counts[(nj, nm)] += 1
            else:
                weight = OVERSAMPLE_WEIGHTS.get((nj, nm), DEFAULT_WEIGHT)
                for _ in range(weight):
                    train_lines.append(text)
                size_train_counts[(nj, nm)] += weight

    rng.shuffle(train_lines)
    rng.shuffle(val_lines)

    with open(args.train_out, "w") as f:
        for t in train_lines:
            f.write(json.dumps({"text": t}) + "\n")
    with open(args.val_out, "w") as f:
        for t in val_lines:
            f.write(json.dumps({"text": t}) + "\n")

    print(f"Instances: {len(instance_ids)} total | {len(train_ids)} train | {len(val_ids)} val")
    print(f"Train records written (post-oversample): {len(train_lines)}")
    print(f"Val records written (no oversampling):    {len(val_lines)}")
    print()
    print(f"{'size':<10}{'train(weighted)':<18}{'val':<10}")
    for size in sorted(set(size_train_counts) | set(size_val_counts)):
        print(f"{size[0]}x{size[1]:<8}{size_train_counts[size]:<18}{size_val_counts[size]:<10}")


if __name__ == "__main__":
    main()