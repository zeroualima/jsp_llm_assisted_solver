import json
import re
from collections import Counter

INPUT = "../v4_eval_results.jsonl"
OUTPUT = "../v4_eval_results_reparsed.jsonl"

# Recognized key variants seen in raw output, in order of "closeness to expected"
KEY_PATTERN = re.compile(
    r'"(op_array|assignment|assignation|assignations|ast|machines|setups)"\s*:\s*\[?([^\]]*)\]?'
)

def extract_array_and_key(raw_text):
    """Find whichever known key appears, pull the integers after it."""
    m = KEY_PATTERN.search(raw_text)
    if not m:
        return None, None
    key = m.group(1)
    nums = re.findall(r'-?\d+', m.group(2))
    if not nums:
        return key, None
    return key, [int(n) for n in nums]


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


def needs_instance_data(rec):
    """We don't have durations/machines stored in the eval file - need to reload from val_1950.jsonl"""
    pass


def main():
    # Load original instance definitions (durations/machines) by id, since
    # v4_eval_results.jsonl doesn't store them.
    instances = {}
    with open("../val_1950.jsonl") as f:
        for line in f:
            rec = json.loads(line)
            instances[rec["id"]] = {
                "num_jobs": rec["num_jobs"],
                "num_machines": rec["num_machines"],
                "durations": rec["durations"],
                "machines": rec["machines"],
            }

    key_counter = Counter()
    format_counter = Counter()  # "clean" vs "needed_reparse"

    with open(INPUT) as fin, open(OUTPUT, "w") as fout:
        for line in fin:
            rec = json.loads(line)
            raw = rec["raw_output"]
            instance = instances[rec["id"]]
            expected_length = rec["num_jobs"] * rec["num_machines"]

            key, array = extract_array_and_key(raw)
            key_counter[key] += 1

            clean_format = raw.strip().startswith('{"op_array"') or raw.strip().startswith('"op_array"')
            rec["response_format"] = "clean" if (clean_format and key == "op_array") else "needed_reparse"
            rec["detected_key"] = key
            format_counter[rec["response_format"]] += 1

            if array is None:
                rec["full"] = {"feasible": False, "reason": "No array could be extracted at all.", "makespan": None}
                rec["gap_percent_full"] = None
            else:
                full_res = evaluate_operation_array(instance, array)
                rec["full"] = full_res
                if full_res["feasible"]:
                    rec["gap_percent_full"] = round(
                        100 * (full_res["makespan"] - rec["best_makespan"]) / rec["best_makespan"], 3)
                else:
                    rec["gap_percent_full"] = None

                # truncated check if array too long but at least expected_length present
                if not full_res["feasible"] and len(array) >= expected_length:
                    trunc_res = evaluate_operation_array(instance, array[:expected_length])
                    rec["truncated"] = trunc_res
                    if trunc_res["feasible"]:
                        rec["gap_percent_truncated"] = round(
                            100 * (trunc_res["makespan"] - rec["best_makespan"]) / rec["best_makespan"], 3)
                else:
                    rec["truncated"] = rec.get("truncated")

            rec["num_parsed_elements"] = len(array) if array else 0
            fout.write(json.dumps(rec) + "\n")

    print("Key distribution:", key_counter)
    print("Format distribution:", format_counter)


if __name__ == "__main__":
    main()
