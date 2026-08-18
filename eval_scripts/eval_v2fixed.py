"""
eval_v2fixed.py

Runs the V2-fixed adapter over all 1950 instances in val_1950.jsonl and records,
per instance: the raw output, how it had to be parsed (clean / needed_reparse /
unparseable), and whether the resulting matrix is structurally valid (each
machine row is a permutation of 0..num_jobs-1).

Deliberately does NOT attempt cycle detection or makespan computation here --
that is a separate downstream step run via MiniZinc/CP-SAT on the structurally
valid subset.

Output: one JSON line per instance, checkpointed (safe to resume after a crash
or SLURM timeout).
"""

import json
import os
import re
import time
import argparse
from collections import Counter

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from transformers import StoppingCriteria, StoppingCriteriaList
from peft import PeftModel
from huggingface_hub import login

MODEL_ID = "meta-llama/Meta-Llama-3.1-8B-Instruct"
ADAPTER_ID = "mazerouali/jsp-llama-v2_fixed-adapter"

# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------

class StopOnString(StoppingCriteria):
    def __init__(self, tokenizer, stop_string, prompt_len):
        self.tokenizer = tokenizer
        self.stop_string = stop_string
        self.prompt_len = prompt_len

    def __call__(self, input_ids, scores, **kwargs):
        text = self.tokenizer.decode(input_ids[0][self.prompt_len:], skip_special_tokens=True)
        return self.stop_string in text


def generate_sequences(model, tokenizer, instance, max_new_tokens):
    prompt = f"<prompt>{json.dumps(instance)}</prompt><completion>"
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    prompt_len = inputs["input_ids"].shape[1]
    stopping_criteria = StoppingCriteriaList([StopOnString(tokenizer, "</completion>", prompt_len)])

    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=[tokenizer.eos_token_id, tokenizer.convert_tokens_to_ids("<|eot_id|>")],
            stopping_criteria=stopping_criteria,
        )
    return tokenizer.decode(out[0], skip_special_tokens=True)[len(prompt):]


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

# Generic row extractor: captures any run of comma-separated integers that is
# immediately followed by a closing bracket "]", regardless of whether the
# opening "[" is present or well-formed. This recovers rows even when the
# model drops the opening bracket, prefixes a row label ("0:", "1.", etc.),
# or otherwise mangles the JSON structure -- as long as each row still ends
# cleanly with "]", which held in every sample seen so far.
ROW_PATTERN = re.compile(r'(-?\d+(?:\s*,\s*-?\d+)+)\s*\]')


def try_strict_json(raw_text):
    """Attempt an exact parse: expects a JSON object with a "sequences" key
    holding a list of lists of ints. Returns the matrix or None."""
    text = raw_text
    if "</completion>" in text:
        text = text.split("</completion>")[0]
    text = text.strip()
    if not text.startswith("{"):
        text = "{" + text if text.startswith('"') else text
    try:
        parsed = json.loads(text)
    except Exception:
        return None, None
    if not isinstance(parsed, dict):
        return None, None
    # look for the exact expected key first
    if "sequences" in parsed:
        return "sequences", parsed["sequences"]
    # otherwise report whichever single key is present, for bookkeeping
    if len(parsed) == 1:
        k = list(parsed.keys())[0]
        return k, parsed[k]
    return None, None


def extract_rows_permissive(raw_text, expected_rows, expected_cols):
    """Fallback: pull out every '<ints>]' run in the text and take it as a
    candidate row, regardless of surrounding JSON validity. Returns the list
    of rows (as lists of ints) if it finds exactly expected_rows rows each of
    length expected_cols; otherwise returns None."""
    text = raw_text
    if "</completion>" in text:
        text = text.split("</completion>")[0]

    matches = ROW_PATTERN.findall(text)
    rows = []
    for m in matches:
        nums = [int(x.strip()) for x in m.split(",")]
        rows.append(nums)

    if len(rows) != expected_rows:
        return None
    if any(len(r) != expected_cols for r in rows):
        return None
    return rows


def parse_response(raw_text, num_jobs, num_machines):
    """
    Returns (response_format, matrix_or_None, detected_key_or_None)
    response_format in {"clean", "needed_reparse", "unparseable"}
    """
    key, matrix = try_strict_json(raw_text)

    if key == "sequences" and isinstance(matrix, list) \
            and len(matrix) == num_machines \
            and all(isinstance(row, list) and len(row) == num_jobs for row in matrix):
        return "clean", matrix, key

    # strict JSON parsed but wrong key / wrong shape -- still worth recording the key
    detected_key = key

    # try permissive row extraction (covers non-JSON, missing brackets, prose, etc.)
    rows = extract_rows_permissive(raw_text, num_machines, num_jobs)
    if rows is not None:
        return "needed_reparse", rows, detected_key

    # if strict JSON gave a matrix of some shape but not matching dimensions,
    # still report it as needed_reparse with whatever shape it has, so the
    # structural validity check below can flag it explicitly as wrong-shape
    if matrix is not None and isinstance(matrix, list):
        return "needed_reparse", matrix, detected_key

    return "unparseable", None, detected_key


def check_structural_validity(matrix, num_jobs, num_machines):
    """Each row must be a permutation of 0..num_jobs-1; there must be exactly
    num_machines rows."""
    if matrix is None:
        return False, "No matrix recovered."
    if not isinstance(matrix, list) or len(matrix) != num_machines:
        got = len(matrix) if isinstance(matrix, list) else "n/a"
        return False, f"Wrong row count: got {got}, expected {num_machines}."

    for i, row in enumerate(matrix):
        if not isinstance(row, list) or len(row) != num_jobs:
            got = len(row) if isinstance(row, list) else "n/a"
            return False, f"Row {i}: wrong length {got}, expected {num_jobs}."
        if any(not isinstance(x, int) for x in row):
            return False, f"Row {i}: contains non-integer elements."
        if any(x < 0 or x >= num_jobs for x in row):
            return False, f"Row {i}: job index out of range 0..{num_jobs - 1}."
        counts = Counter(row)
        if any(counts[j] != 1 for j in range(num_jobs)):
            return False, f"Row {i}: not a permutation of 0..{num_jobs - 1} (duplicate/missing job)."

    return True, None


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="val_1950.jsonl")
    parser.add_argument("--output", default="v2fixed_eval_results.jsonl")
    parser.add_argument("--max_new_tokens", type=int, default=1000)
    args = parser.parse_args()

    login(token=os.environ["HF_TOKEN"])

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    tokenizer.pad_token = tokenizer.eos_token

    base = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True,
        ),
        device_map="auto",
    )
    model = PeftModel.from_pretrained(base, ADAPTER_ID, adapter_name="v2fixed")
    model.set_adapter("v2fixed")
    model.eval()
    assert model.active_adapter == "v2fixed"
    print("Model ready, active adapter:", model.active_adapter, flush=True)

    done_ids = set()
    if os.path.exists(args.output):
        with open(args.output) as f:
            for line in f:
                try:
                    done_ids.add(json.loads(line)["id"])
                except Exception:
                    pass
    print(f"Resuming, {len(done_ids)} instances already done.", flush=True)

    with open(args.input) as fin, open(args.output, "a") as fout:
        for line in fin:
            rec = json.loads(line)
            if rec["id"] in done_ids:
                continue

            instance = {
                "num_jobs": rec["num_jobs"],
                "num_machines": rec["num_machines"],
                "durations": rec["durations"],
                "machines": rec["machines"],
            }
            num_jobs = rec["num_jobs"]
            num_machines = rec["num_machines"]

            t0 = time.time()
            raw = generate_sequences(model, tokenizer, instance, args.max_new_tokens)
            gen_time = time.time() - t0

            response_format, matrix, detected_key = parse_response(raw, num_jobs, num_machines)
            valid, reason = check_structural_validity(matrix, num_jobs, num_machines)

            result_entry = {
                "id": rec["id"],
                "num_jobs": num_jobs,
                "num_machines": num_machines,
                "best_makespan": rec["best_makespan"],
                "is_optimal": rec["is_optimal"],
                "generation_time_sec": round(gen_time, 2),
                "raw_output": raw,
                "response_format": response_format,
                "detected_key": detected_key,
                "structural_validity": valid,
                "structural_invalid_reason": reason,
                "extracted_matrix": matrix,
            }

            fout.write(json.dumps(result_entry) + "\n")
            fout.flush()
            print(f"{rec['id']} ({num_jobs}x{num_machines}): {gen_time:.1f}s, "
                  f"format={response_format}, valid={valid}", flush=True)


if __name__ == "__main__":
    main()
