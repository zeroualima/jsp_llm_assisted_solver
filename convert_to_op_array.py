"""
Convert train_ft.jsonl / val_ft.jsonl (start-times completion format) to
Bierwirth operation-array completion format.

Input completion:  {"starts": [[0, 4, 11], [4, 5, 15], [14, 15, 16]]}
Output completion: {"op_array": [1, 0, 1, 0, 2, 1, 2, 0, 2]}

The op_array is a permutation of length J*M where job j appears exactly M
times. Each occurrence of j refers to j's next unscheduled operation.
Ties in start time are broken by job_id (ascending) -- this convention is
baked into encode_to_operation_array and must be kept consistent at inference.

Usage:
    python3 convert_to_op_array.py --train train_ft.jsonl --val val_ft.jsonl --train-out train_ft_op.jsonl --val-out val_ft_op.jsonl
"""

import json
import argparse
import re
from collections import Counter


# ---------------------------------------------------------------------------
# Bierwirth encoding
# ---------------------------------------------------------------------------

def encode_to_operation_array(instance, start_times):
    num_jobs     = instance["num_jobs"]
    num_machines = instance["num_machines"]
    operations   = []
    for j in range(num_jobs):
        for i in range(num_machines):
            operations.append((start_times[j][i], j, i))
    operations.sort()           # sort by start_time, then job_id (tie-break)
    return [op[1] for op in operations]


def validate_op_array(op_array, num_jobs, num_machines):
    expected = num_jobs * num_machines
    if len(op_array) != expected:
        return False, f"length {len(op_array)} != {expected}"
    counts = Counter(op_array)
    for j in range(num_jobs):
        if counts[j] != num_machines:
            return False, f"job {j} appears {counts[j]} times, expected {num_machines}"
    return True, None


# ---------------------------------------------------------------------------
# Line conversion
# ---------------------------------------------------------------------------

def convert_line(line):
    line = line.strip()
    if not line:
        return None, None

    rec  = json.loads(line)
    text = rec["text"]

    # --- Extract prompt JSON (instance) ---
    prompt_match = re.search(r"<prompt>(.*?)</prompt>", text, re.DOTALL)
    if not prompt_match:
        return None, "no <prompt> tag"
    instance = json.loads(prompt_match.group(1))

    # --- Extract completion JSON (starts) ---
    comp_match = re.search(r"<completion>(.*?)</completion>", text, re.DOTALL)
    if not comp_match:
        return None, "no <completion> tag"

    comp_text = comp_match.group(1).strip()
    if not comp_text.startswith("{"):
        comp_text = "{\"" + comp_text     # repair missing leading `{"`

    parsed      = json.loads(comp_text)
    start_times = parsed["starts"]        # [[s00, s01, ...], ...]

    # --- Encode ---
    op_array = encode_to_operation_array(instance, start_times)

    # --- Validate (catches any encoding bug immediately) ---
    ok, reason = validate_op_array(
        op_array, instance["num_jobs"], instance["num_machines"]
    )
    if not ok:
        return None, f"invalid op_array: {reason}"

    # --- Rebuild text with new completion ---
    new_completion = json.dumps({"op_array": op_array})
    new_text = (
        text[:comp_match.start()]
        + f"<completion>{new_completion}</completion>"
    )
    return json.dumps({"text": new_text}), None


# ---------------------------------------------------------------------------
# File conversion
# ---------------------------------------------------------------------------

def convert_file(in_path, out_path):
    converted = failed = 0
    with open(in_path) as f_in, open(out_path, "w") as f_out:
        for lineno, line in enumerate(f_in, 1):
            result, err = convert_line(line)
            if result:
                f_out.write(result + "\n")
                converted += 1
            elif err:
                print(f"  [WARN] line {lineno}: {err}")
                failed += 1
    print(f"  {in_path} -> {out_path}")
    print(f"    converted: {converted}  |  failed: {failed}")
    return converted


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train",     required=True)
    parser.add_argument("--val",       required=True)
    parser.add_argument("--train-out", required=True)
    parser.add_argument("--val-out",   required=True)
    args = parser.parse_args()

    print("Converting to Bierwirth operation-array format...\n")
    n_train = convert_file(args.train, args.train_out)
    n_val   = convert_file(args.val,   args.val_out)

    print(f"\nTotal: {n_train} train  |  {n_val} val")

    # --- Spot-check: decode one example and verify round-trip ---
    print("\n--- Sample from train (first line) ---")
    with open(args.train_out) as f:
        sample = json.loads(f.readline())
    text = sample["text"]
    comp = re.search(r"<completion>(.*?)</completion>", text).group(1)
    op_array = json.loads(comp)["op_array"]
    print(f"op_array length: {len(op_array)}")
    print(f"first 20 elements: {op_array[:20]}")

    # Verify counts
    with open(args.train_out) as f:
        first = json.loads(f.readline())
    prompt_str = re.search(r"<prompt>(.*?)</prompt>",
                           first["text"]).group(1)
    inst = json.loads(prompt_str)
    ok, reason = validate_op_array(
        op_array, inst["num_jobs"], inst["num_machines"]
    )
    print(f"Validation: {'OK' if ok else 'FAILED -- ' + reason}")


if __name__ == "__main__":
    main()
