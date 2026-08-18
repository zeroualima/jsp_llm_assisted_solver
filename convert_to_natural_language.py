"""
Convert train_ft.jsonl and val_ft.jsonl from JSON sequence format to
natural language completion format.

Input completion:
    <completion>{"sequences": [[2,0,1],[1,2,0],[0,1,2]]}</completion>

Output completion:
    <completion>A good quality jobshop schedule is:
Machine 1: process jobs in order 3, 1, 2
Machine 2: process jobs in order 2, 3, 1
Machine 3: process jobs in order 1, 2, 3</completion>

Jobs and machines are 1-indexed in the natural language output.
The parser at inference time must subtract 1 to recover 0-indexed sequences.

Usage:
    python3 convert_to_natural_language.py \
        --train train_ft.jsonl --val val_ft.jsonl \
        --train-out train_ft_nl.jsonl --val-out val_ft_nl.jsonl
"""

import json
import argparse
import re


def sequences_to_natural_language(sequences):
    """
    sequences: list[num_machines] of list[num_jobs] -- 0-indexed job ids.
    Returns natural language string with 1-indexed machines and jobs.
    """
    lines = ["A good quality jobshop schedule is:"]
    for m, seq in enumerate(sequences):
        jobs_str = ", ".join(str(j + 1) for j in seq)
        lines.append(f"Machine {m + 1}: process jobs in order {jobs_str}")
    return "\n".join(lines)


def convert_line(line):
    line = line.strip()
    if not line:
        return None

    rec = json.loads(line)
    text = rec["text"]

    # Extract completion content between <completion> and </completion>
    match = re.search(r"<completion>(.*?)</completion>", text, re.DOTALL)
    if not match:
        raise ValueError(f"No <completion> tag found in: {text[:100]}")

    completion_json = match.group(1).strip()
    parsed = json.loads(completion_json)
    sequences = parsed["sequences"]

    nl_completion = sequences_to_natural_language(sequences)

    # Replace the completion part, keep the prompt identical
    new_text = text[:match.start()] + \
               f"<completion>{nl_completion}</completion>"

    return json.dumps({"text": new_text})


def convert_file(in_path, out_path):
    converted = 0
    failed = 0
    with open(in_path) as f_in, open(out_path, "w") as f_out:
        for line in f_in:
            try:
                result = convert_line(line)
                if result:
                    f_out.write(result + "\n")
                    converted += 1
            except Exception as e:
                print(f"[WARN] Failed to convert line: {e}")
                failed += 1
    print(f"  {in_path} -> {out_path}: {converted} converted, {failed} failed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train",     required=True)
    parser.add_argument("--val",       required=True)
    parser.add_argument("--train-out", required=True)
    parser.add_argument("--val-out",   required=True)
    args = parser.parse_args()

    print("Converting to natural language format...")
    convert_file(args.train, args.train_out)
    convert_file(args.val,   args.val_out)

    # Spot-check: print one example from each output
    print("\n--- Sample from train ---")
    with open(args.train_out) as f:
        sample = json.loads(f.readline())
    prompt_end = sample["text"].index("</prompt>") + len("</prompt>")
    print(sample["text"][prompt_end:])

    print("\n--- Sample from val ---")
    with open(args.val_out) as f:
        sample = json.loads(f.readline())
    print(sample["text"][sample["text"].index("</prompt>") + len("</prompt>"):])


if __name__ == "__main__":
    main()
