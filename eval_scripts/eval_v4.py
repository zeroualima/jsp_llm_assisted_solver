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
ADAPTER_ID = "mazerouali/jsp-llama-v4-adapter"


def evaluate_operation_array(instance, op_array):
    num_jobs = instance["num_jobs"]
    num_machines = instance["num_machines"]
    durations = instance["durations"]
    machines = instance["machines"]

    expected_length = num_jobs * num_machines
    if len(op_array) != expected_length:
        return {"feasible": False,
                "reason": f"Invalid length: {len(op_array)} elements, expected {expected_length}.",
                "makespan": None}

    if any(job < 0 or job >= num_jobs for job in op_array):
        return {"feasible": False, "reason": "Invalid job index out of range.", "makespan": None}

    counts = Counter(op_array)
    for j in range(num_jobs):
        if counts[j] != num_machines:
            return {"feasible": False,
                     "reason": f"Job {j} appears {counts[j]} times, expected {num_machines}.",
                     "makespan": None}

    job_next_op_idx = [0] * num_jobs
    job_end_times = [0] * num_jobs
    machine_end_times = [0] * num_machines

    for job in op_array:
        op_idx = job_next_op_idx[job]
        machine = machines[job][op_idx]
        duration = durations[job][op_idx]
        start = max(job_end_times[job], machine_end_times[machine])
        end = start + duration
        job_end_times[job] = end
        machine_end_times[machine] = end
        job_next_op_idx[job] += 1

    return {"feasible": True, "reason": None, "makespan": max(job_end_times)}


def extract_op_array(raw_text):
    """Pull whatever integers appear inside op_array, whether or not the JSON closed cleanly."""
    m = re.search(r'"op_array"\s*:\s*\[([^\]]*)', raw_text)
    if not m:
        return None
    nums = re.findall(r'-?\d+', m.group(1))
    return [int(n) for n in nums] if nums else None


class StopOnString(StoppingCriteria):
    def __init__(self, tokenizer, stop_string, prompt_len):
        self.tokenizer = tokenizer
        self.stop_string = stop_string
        self.prompt_len = prompt_len

    def __call__(self, input_ids, scores, **kwargs):
        text = self.tokenizer.decode(input_ids[0][self.prompt_len:], skip_special_tokens=True)
        return self.stop_string in text


def generate_op_array(model, tokenizer, instance, max_new_tokens=1000):
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="val_1950.jsonl")
    parser.add_argument("--output", default="v4_eval_results.jsonl")
    parser.add_argument("--max_new_tokens", type=int, default=1000)
    args = parser.parse_args()

    # HF_TOKEN must be set as an environment variable in the SLURM script
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
    model = PeftModel.from_pretrained(base, ADAPTER_ID)
    model.eval()
    print("Model ready.", flush=True)

    # Resume support: skip ids already present in the output file
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
            expected_length = rec["num_jobs"] * rec["num_machines"]

            t0 = time.time()
            raw = generate_op_array(model, tokenizer, instance, args.max_new_tokens)
            gen_time = time.time() - t0

            op_array = extract_op_array(raw)

            result_entry = {
                "id": rec["id"],
                "num_jobs": rec["num_jobs"],
                "num_machines": rec["num_machines"],
                "best_makespan": rec["best_makespan"],
                "is_optimal": rec["is_optimal"],
                "generation_time_sec": round(gen_time, 2),
                "raw_output": raw,
                "num_parsed_elements": len(op_array) if op_array else 0,
                "expected_elements": expected_length,
            }

            if op_array is None:
                result_entry["full"] = {"feasible": False, "reason": "No op_array found in output.", "makespan": None}
                result_entry["truncated"] = None
            else:
                full_res = evaluate_operation_array(instance, op_array)
                result_entry["full"] = full_res
                if full_res["feasible"]:
                    result_entry["gap_percent_full"] = round(
                        100 * (full_res["makespan"] - rec["best_makespan"]) / rec["best_makespan"], 3)

                # If length doesn't match but we have at least enough elements, test the truncated prefix
                if not full_res["feasible"] and op_array is not None and len(op_array) >= expected_length:
                    trunc_res = evaluate_operation_array(instance, op_array[:expected_length])
                    result_entry["truncated"] = trunc_res
                    if trunc_res["feasible"]:
                        result_entry["gap_percent_truncated"] = round(
                            100 * (trunc_res["makespan"] - rec["best_makespan"]) / rec["best_makespan"], 3)
                else:
                    result_entry["truncated"] = None

            fout.write(json.dumps(result_entry) + "\n")
            fout.flush()
            print(f"{rec['id']} ({rec['num_jobs']}x{rec['num_machines']}): "
                  f"{gen_time:.1f}s, feasible={result_entry['full']['feasible']}", flush=True)


if __name__ == "__main__":
    main()
