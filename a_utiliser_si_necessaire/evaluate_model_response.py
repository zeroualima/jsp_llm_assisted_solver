import json
from llm import generate_continuation

def fill_seq(num_jobs, num_machines, machines):
    sequences = [[] for _ in range(num_machines)]
    for j in range(num_jobs):
        for i in range(num_machines):
            m = machines[j][i]
            sequences[m].append((j, i))
    return sequences

def sort_seq(sequences, starts):
    for m in range(len(sequences)):
        sequences[m].sort(key=lambda task: starts[task[0]][task[1]])
    return sequences

def sequences(num_jobs, num_machines, machines, starts) :
    tmp = fill_seq(num_jobs, num_machines, machines)
    return sort_seq(tmp, starts)

def check_shape(num_jobs, num_machines, model_starts):
    if not isinstance(model_starts, list) or len(model_starts) != num_jobs:
        return False
    for job_row in model_starts:
        if not isinstance(job_row, list) or len(job_row) != num_machines:
            return False
        if not all(isinstance(v, int) for v in job_row):
            return False
    return True

def check_monotonic_order(num_jobs, num_machines, starts):
    """True if every job's start times are non-decreasing (no reversed order)."""
    for j in range(num_jobs):
        for i in range(num_machines - 1):
            if starts[j][i] > starts[j][i + 1]:
                return False
    return True


def check_precedence(num_jobs, num_machines, durations, starts):
    for j in range(num_jobs):
        for i in range(num_machines - 1):
            if starts[j][i] + durations[j][i] > starts[j][i + 1]:
                return False
    return True


def check_overlap(durations, starts, sequences):
    """sequences: one list per machine, each containing (j, i) pairs sorted by start time."""
    num_machines = len(sequences)
    for m in range(num_machines):
        ops = sequences[m]
        for idx in range(len(ops) - 1):
            j1, i1 = ops[idx]
            j2, i2 = ops[idx + 1]
            if starts[j1][i1] + durations[j1][i1] > starts[j2][i2]:
                return False
    return True


def compute_makespan(num_jobs, num_machines, durations, starts):
    return max(
        starts[j][num_machines - 1] + durations[j][num_machines - 1]
        for j in range(num_jobs)
    )


def compute_gap_percent(model_makespan, best_known_makespan):
    return (model_makespan - best_known_makespan) * 100.0 / best_known_makespan


def get_best_known_makespan(dataset_records_for_instance):
    """dataset_records_for_instance: list of solution records sharing the same instance ID."""
    best = min(rec["solution"]["makespan"] for rec in dataset_records_for_instance)
    return best


def validate_instance(line, sibling_records):
    """
    line: one JSONL record (used for instance + as one reference solution)
    sibling_records: ALL records sharing this instance's ID (for best_known_makespan and for later sequencing comparison)
    """
    record = json.loads(line)
    report = {"instance_id": record["instance"]["id"]}

    num_jobs = record["instance"]["num_jobs"]
    num_machines = record["instance"]["num_machines"]
    durations = record["instance"]["durations"]
    machines = record["instance"]["machines"]

    instance = {
        "num_jobs": num_jobs, "num_machines": num_machines,
        "durations": durations, "machines": machines
    }
    prompt = f"<prompt>{json.dumps(instance)}</prompt><completion>"
    model_continuation = generate_continuation(prompt, max_new_tokens=300)

    report["failure_reason"] = []

    # --- Parse ---
    try:
        model_starts = parse_model_starts(model_continuation)
    except (json.JSONDecodeError, KeyError, IndexError):
        report["failure_reason"].append("malformed_json")
        report["feasible"] = False
        report["model_makespan"] = None
        report["gap_percent"] = None
        report["sequence_extractable"] = False
        return report

    # --- Shape check (must pass before any indexing below) ---
    if not check_shape(num_jobs, num_machines, model_starts):
        report["failure_reason"].append("wrong_shape")
        report["feasible"] = False
        report["model_makespan"] = None
        report["gap_percent"] = None
        report["sequence_extractable"] = False
        return report

    # --- Monotonic order check (determines if sequencing is even meaningful) ---
    monotonic = check_monotonic_order(num_jobs, num_machines, model_starts)
    report["sequence_extractable"] = monotonic
    if not monotonic:
        report["failure_reason"].append("reversed_task_order")

    # --- Feasibility checks ---
    precedence_ok = check_precedence(num_jobs, num_machines, durations, model_starts)
    if not precedence_ok:
        report["failure_reason"].append("precedence_violation")

    sequences = fill_seq(num_jobs, num_machines, machines)
    sequences = sort_seq(sequences, model_starts)
    overlap_ok = check_overlap(durations, model_starts, sequences)
    if not overlap_ok:
        report["failure_reason"].append("overlap_violation")

    report["feasible"] = (precedence_ok and overlap_ok)

    # --- Makespan / gap (only meaningful if feasible) ---
    if report["feasible"]:
        model_makespan = compute_makespan(num_jobs, num_machines, durations, model_starts)
        best_known = get_best_known_makespan(sibling_records)
        report["model_makespan"] = model_makespan
        report["gap_percent"] = compute_gap_percent(model_makespan, best_known)
    else:
        report["model_makespan"] = None
        report["gap_percent"] = None

    # --- Always extract the "best-effort" sequencing, for later comparison ---
    # (sort_seq already ignores feasibility — this works even on a broken solution,
    #  as long as monotonic order held; if it didn't, flag it but still return it
    #  for inspection, the caller can decide to discard it)
    report["model_sequences"] = sequences

    return report