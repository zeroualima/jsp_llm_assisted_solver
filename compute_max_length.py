"""
Compute the actual maximum token length across all examples in train_ft.jsonl
and val_ft.jsonl, so max_length in finetune.py is grounded in real data
rather than a guess.

Writes max_length.json alongside the output files so finetune.py can read it.

Usage:
    python3 compute_max_length.py \
        --train train_ft.jsonl --val val_ft.jsonl \
        --model meta-llama/Meta-Llama-3.1-8B-Instruct \
        --margin 1.10 \
        --out max_length.json
"""

import json
import argparse
import os
from transformers import AutoTokenizer

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train",   required=True)
    parser.add_argument("--val",     required=True)
    parser.add_argument("--model",   default="meta-llama/Meta-Llama-3.1-8B-Instruct")
    parser.add_argument("--margin",  type=float, default=1.10,
                        help="Multiply observed max by this safety margin")
    parser.add_argument("--out",     default="max_length.json")
    args = parser.parse_args()

    hf_token = os.environ.get("HF_TOKEN")
    print(f"Loading tokenizer: {args.model}")
    tokenizer = AutoTokenizer.from_pretrained(args.model, token=hf_token)
    tokenizer.pad_token = tokenizer.eos_token

    max_len = 0
    total = 0
    over_2048 = 0
    over_4096 = 0
    lengths = []

    for path in [args.train, args.val]:
        label = os.path.basename(path)
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                text = rec["text"]
                n = len(tokenizer(text, add_special_tokens=True)["input_ids"])
                lengths.append(n)
                total += 1
                if n > max_len:
                    max_len = n
                if n > 2048:
                    over_2048 += 1
                if n > 4096:
                    over_4096 += 1
                if total % 10000 == 0:
                    print(f"  Processed {total} examples, max so far: {max_len}")

    lengths.sort()
    p50 = lengths[len(lengths) // 2]
    p95 = lengths[int(len(lengths) * 0.95)]
    p99 = lengths[int(len(lengths) * 0.99)]
    recommended = int(max_len * args.margin)
    # Round up to nearest multiple of 64 (common for GPU memory efficiency)
    recommended = ((recommended + 63) // 64) * 64

    result = {
        "total_examples": total,
        "max_tokens_observed": max_len,
        "p50_tokens": p50,
        "p95_tokens": p95,
        "p99_tokens": p99,
        "examples_over_2048": over_2048,
        "examples_over_4096": over_4096,
        "margin_applied": args.margin,
        "recommended_max_length": recommended,
    }

    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)

    print()
    print("=" * 60)
    print(f"Total examples tokenized:  {total}")
    print(f"Max tokens observed:       {max_len}")
    print(f"p50 / p95 / p99:           {p50} / {p95} / {p99}")
    print(f"Examples exceeding 2048:   {over_2048} ({100*over_2048/total:.1f}%)")
    print(f"Examples exceeding 4096:   {over_4096} ({100*over_4096/total:.1f}%)")
    print(f"Recommended max_length:    {recommended}  (observed max x{args.margin}, rounded to 64)")
    print(f"Written to:                {args.out}")
    print("=" * 60)
    if over_2048 > 0:
        print(f"\nWARNING: {over_2048} examples would have been TRUNCATED by the")
        print(f"original max_length=2048. Set MAX_SEQ_LEN={recommended} in finetune.py.")

if __name__ == "__main__":
    main()