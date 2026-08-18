"""
eval_v3.py

Runs the V3 adapter (natural-language per-machine sequences) over all 1950
instances in val_1950.jsonl and records, per instance: the raw output, how
it had to be parsed, and whether the resulting matrix is structurally valid.

Training format (1-indexed in the text):
    A good quality jobshop schedule is:
    Machine 1: process jobs in order 1, 3, 2
    Machine 2: process jobs in order 3, 2, 1
    ...

Note the mismatch with instance/job indexing elsewhere in the pipeline
(0-indexed): machine "Machine k" and job numbers in the text are 1-indexed
here, and are converted to 0-indexed on extraction so structural validity
can be checked against 0..num_jobs-1 / 0..num_machines-1 exactly as for
V2-fixed and V4.

Does NOT attempt cycle detection or makespan computation -- same as
eval_v2fixed.py, that is a separate downstream MiniZinc/CP-SAT step.

Output: one JSON line per instance, checkpointed (safe to resume).
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
ADAPTER_ID = "mazerouali/jsp-llama-v3-adapter"

EXPECTED_PREAMBLE = "A good quality jobshop schedule is:"

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


def generate_sequences_text(model, tokenizer, instance, max_new_tokens):
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

# Permissive row extractor: matches "Machine <k>: process jobs in order <list>"
# regardless of surrounding text, missing preamble, extra whitespace, or
# whether machines appear in order. Captures up to the next "Machine <k>:"
# occurrence or the end of the string, so trailing prose after the last row
# doesn't get swept into it.
ROW_PATTERN = re.compile(
    r'Machine\s*(\d+)\s*:\s*process jobs in order\s*([\d,\s]+?)'
    r'(?=(?:Machine\s*\d+\s*:)|\Z)',
    re.IGNORECASE | re.DOTALL,
)


def extract_rows(raw_text, num_jobs, num_machines):
    """
    Returns (matrix_or_None, is_exact_clean_template)
    matrix rows are 0-indexed job lists, ordered by machine index 0..num_machines-1.
    """
    text = raw_text
    if "</completion>" in text:
        text = text.split("</completion>")[0]

    matches = ROW_PATTERN.findall(text)
    if len(matches) != num_machines:
        return None, False

    rows_by_machine = {}
    for machine_str, jobs_str in matches:
        machine_idx = int(machine_str) - 1  # 1-indexed in text -> 0-indexed
        job_nums = re.findall(r'\d+', jobs_str)
        if len(job_nums) != num_jobs:
            return None, False
        jobs_0indexed = [int(j) - 1 for j in job_nums]  # 1-indexed in text -> 0-indexed
        rows_by_machine[machine_idx] = jobs_0indexed

    if set(rows_by_machine.keys()) != set(range(num_machines)):
        # machines mentioned don't exactly cover 0..num_machines-1 once each
        return None, False

    matrix = [rows_by_machine[m] for m in range(num_machines)]

    # Check for exact clean template: preamble present, machines in order
    # 1..num_machines, no stray text between rows.
    stripped = text.strip()
    is_clean = stripped.startswith(EXPECTED_PREAMBLE)
    if is_clean:
        # rebuild what the exact expected string would look like and compare
        # loosely (allow trailing whitespace differences) machine ordering
        machine_order = [int(m) for m, _ in matches]
        is_clean = machine_order == list(range(1, num_machines + 1))

    return matrix, is_clean


def parse_response(raw_text, num_jobs, num_machines):
    """
    Returns (response_format, matrix_or_None)
    response_format in {"clean", "needed_reparse", "unparseable"}
    """
    matrix, is_clean = extract_rows(raw_text, num_jobs, num_machines)

    if matrix is None:
        return "unparseable", None
    if is_clean:
        return "clean", matrix
    return "needed_reparse", matrix


def check_structural_validity(matrix, num_jobs, num_machines):
    if matrix is None:
        return False, "No matrix recovered."
    if not isinstance(matrix, list) or len(matrix) != num_machines:
        got = len(matrix) if isinstance(matrix, list) else "n/a"
        return False, f"Wrong row count: got {got}, expected {num_machines}."

    for i, row in enumerate(matrix):
        if not isinstance(row, list) or len(row) != num_jobs:
            got = len(row) if isinstance(row, list) else "n/a"
            return False, f"Row {i}: wrong length {got}, expected {num_jobs}."
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
    parser.add_argument("--output", default="v3_eval_results.jsonl")
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
    model = PeftModel.from_pretrained(base, ADAPTER_ID, adapter_name="v3")
    model.set_adapter("v3")
    model.eval()
    assert model.active_adapter == "v3"
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
            raw = generate_sequences_text(model, tokenizer, instance, args.max_new_tokens)
            gen_time = time.time() - t0

            response_format, matrix = parse_response(raw, num_jobs, num_machines)
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
