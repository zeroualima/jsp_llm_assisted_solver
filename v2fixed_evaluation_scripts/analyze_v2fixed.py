"""
analyze_v2fixed.py

Reads v2fixed_eval_results.jsonl and produces:
  - v2fixed_report.txt   : human-readable summary report
  - v2fixed_by_size.csv   : per-instance-size table
  - v2fixed_overall.csv   : single-row overall summary table

Mirrors analyze_v4.py, adapted for the sequences-matrix format. Note: unlike
V4, no gap%/makespan figures are computed here -- structural validity only
guarantees each machine row is a permutation of the jobs, not that the matrix
is cycle-free. Gap% requires the downstream MiniZinc/CP-SAT pass over the
structurally valid subset (separate script, separate stage).

Run locally on desktop, no cluster/GPU needed.
"""

import json
import csv
from collections import defaultdict
import statistics as st

INPUT = "/home/mazerouali/Desktop/fine_tuning_v3_backup/v3_evaluation/v3_eval_results.jsonl"
REPORT_TXT = "/home/mazerouali/Desktop/fine_tuning_v3_backup/v3_evaluation/v3_report.txt"
BY_SIZE_CSV = "/home/mazerouali/Desktop/fine_tuning_v3_backup/v3_evaluation/v3_by_size.csv"
OVERALL_CSV = "/home/mazerouali/Desktop/fine_tuning_v3_backup/v3_evaluation/v3_overall.csv"


def load_records(path):
    recs = []
    with open(path) as f:
        for line in f:
            recs.append(json.loads(line))
    return recs


def size_key(rec):
    return (rec["num_jobs"], rec["num_machines"])


def safe_mean(values):
    return round(st.mean(values), 3) if values else None


def safe_median(values):
    return round(st.median(values), 3) if values else None


def pct(n, d):
    return round(100 * n / d, 2) if d else None


def main():
    recs = load_records(INPUT)
    total = len(recs)

    by_size = defaultdict(list)
    for r in recs:
        by_size[size_key(r)].append(r)

    # --- Overall summary ---
    n_clean = sum(1 for r in recs if r["response_format"] == "clean")
    n_reparse = sum(1 for r in recs if r["response_format"] == "needed_reparse")
    n_unparseable = sum(1 for r in recs if r["response_format"] == "unparseable")
    n_valid = sum(1 for r in recs if r["structural_validity"])
    n_invalid = total - n_valid

    gen_times = [r["generation_time_sec"] for r in recs]

    overall = {
        "n_instances": total,
        "n_clean_format": n_clean,
        "n_needed_reparse": n_reparse,
        "n_unparseable": n_unparseable,
        "clean_format_rate_pct": pct(n_clean, total),
        "reparse_needed_rate_pct": pct(n_reparse, total),
        "unparseable_rate_pct": pct(n_unparseable, total),
        "n_structurally_valid": n_valid,
        "n_structurally_invalid": n_invalid,
        "structural_validity_rate_pct": pct(n_valid, total),
        "gen_time_mean_sec": safe_mean(gen_times),
        "gen_time_median_sec": safe_median(gen_times),
        "gen_time_max_sec": max(gen_times) if gen_times else None,
    }

    # Cross-tab: validity given format (e.g. how many "needed_reparse" cases were still valid)
    for fmt in ("clean", "needed_reparse", "unparseable"):
        subset = [r for r in recs if r["response_format"] == fmt]
        n_sub = len(subset)
        n_sub_valid = sum(1 for r in subset if r["structural_validity"])
        overall[f"n_{fmt}"] = n_sub
        overall[f"{fmt}_valid_rate_pct"] = pct(n_sub_valid, n_sub)

    # Breakdown of WHY structurally invalid (reason strings), for the invalid subset
    reason_counter = defaultdict(int)
    for r in recs:
        if not r["structural_validity"]:
            reason = r.get("structural_invalid_reason") or "Unknown"
            # bucket by reason prefix (wrong row count / wrong length / not a permutation / no matrix / out of range)
            if reason.startswith("No matrix"):
                bucket = "no_matrix_recovered"
            elif reason.startswith("Wrong row count"):
                bucket = "wrong_row_count"
            elif "wrong length" in reason:
                bucket = "wrong_row_length"
            elif "out of range" in reason:
                bucket = "job_index_out_of_range"
            elif "not a permutation" in reason:
                bucket = "duplicate_or_missing_job"
            elif "non-integer" in reason:
                bucket = "non_integer_elements"
            else:
                bucket = "other"
            reason_counter[bucket] += 1

    # Schema key adherence
    key_counts = defaultdict(int)
    for r in recs:
        key_counts[r.get("detected_key")] += 1

    # --- Per-size breakdown ---
    size_rows = []
    for (nj, nm), group in sorted(by_size.items()):
        n = len(group)
        n_clean_g = sum(1 for r in group if r["response_format"] == "clean")
        n_reparse_g = sum(1 for r in group if r["response_format"] == "needed_reparse")
        n_unparseable_g = sum(1 for r in group if r["response_format"] == "unparseable")
        n_valid_g = sum(1 for r in group if r["structural_validity"])
        gen_times_g = [r["generation_time_sec"] for r in group]

        size_rows.append({
            "num_jobs": nj,
            "num_machines": nm,
            "n_instances": n,
            "n_clean_format": n_clean_g,
            "clean_format_rate_pct": pct(n_clean_g, n),
            "n_needed_reparse": n_reparse_g,
            "reparse_rate_pct": pct(n_reparse_g, n),
            "n_unparseable": n_unparseable_g,
            "unparseable_rate_pct": pct(n_unparseable_g, n),
            "n_structurally_valid": n_valid_g,
            "structural_validity_rate_pct": pct(n_valid_g, n),
            "gen_time_mean_sec": safe_mean(gen_times_g),
            "gen_time_max_sec": round(max(gen_times_g), 2) if gen_times_g else None,
        })

    # --- Write CSVs ---
    with open(BY_SIZE_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(size_rows[0].keys()))
        writer.writeheader()
        writer.writerows(size_rows)

    with open(OVERALL_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(overall.keys()))
        writer.writeheader()
        writer.writerow(overall)

    # --- Write human-readable report ---
    with open(REPORT_TXT, "w") as f:
        f.write("=" * 70 + "\n")
        f.write("V2-FIXED FINE-TUNED MODEL EVALUATION REPORT\n")
        f.write("Per-machine job sequences, val_1950 instance set\n")
        f.write("=" * 70 + "\n\n")

        f.write("-- OVERALL SUMMARY --\n\n")
        f.write(f"Total instances evaluated:              {overall['n_instances']}\n\n")

        f.write("Response format distribution:\n")
        f.write(f"  Clean (exact 'sequences' key, correct shape):  {overall['n_clean_format']} ({overall['clean_format_rate_pct']}%)\n")
        f.write(f"  Needed permissive reparse:                     {overall['n_needed_reparse']} ({overall['reparse_needed_rate_pct']}%)\n")
        f.write(f"  Unparseable (no matrix recoverable at all):    {overall['n_unparseable']} ({overall['unparseable_rate_pct']}%)\n\n")

        f.write("Structural validity (each machine row is a permutation of the jobs):\n")
        f.write(f"  Valid:   {overall['n_structurally_valid']} ({overall['structural_validity_rate_pct']}%)\n")
        f.write(f"  Invalid: {overall['n_structurally_invalid']}\n\n")

        f.write("Structural validity rate WITHIN each format category:\n")
        for fmt in ("clean", "needed_reparse", "unparseable"):
            f.write(f"  {fmt:16s}: {overall[f'n_{fmt}']:5d} instances, {overall[f'{fmt}_valid_rate_pct']}% structurally valid\n")
        f.write("\n")
        f.write("NOTE: unparseable responses are valid 0% of the time by definition\n")
        f.write("(no matrix could be recovered at all). The comparison that matters is\n")
        f.write("between 'clean' and 'needed_reparse': if reparse-recovered matrices are\n")
        f.write("valid about as often as clean ones, the reparse step is recovering\n")
        f.write("genuinely usable data, not noise.\n\n")

        f.write(f"Generation time (sec) - mean: {overall['gen_time_mean_sec']}, "
                f"median: {overall['gen_time_median_sec']}, max: {overall['gen_time_max_sec']}\n\n")

        f.write("-" * 70 + "\n")
        f.write("-- WHY STRUCTURALLY INVALID (breakdown of failure reasons) --\n\n")
        for bucket, count in sorted(reason_counter.items(), key=lambda x: -x[1]):
            f.write(f"  {bucket:28s}: {count:5d}  ({pct(count, n_invalid)}% of invalid, {pct(count, total)}% of total)\n")
        f.write("\n")
        f.write("NOTE: 'duplicate_or_missing_job' is the category most relevant to the\n")
        f.write("triplet-based re-fine-tuning idea (a well-formed matrix with an internal\n")
        f.write("inconsistency). Other categories (wrong row count/length, no matrix\n")
        f.write("recovered) reflect the model failing to produce the expected structure\n")
        f.write("at all, which a cycle/error-correction triplet would not address.\n\n")

        f.write("-" * 70 + "\n")
        f.write("-- SCHEMA KEY ADHERENCE (JSON key detected, where applicable) --\n\n")
        for key, count in sorted(key_counts.items(), key=lambda x: -x[1]):
            label = key if key else "(no key / not JSON)"
            f.write(f"  {label:20s}: {count:5d}  ({pct(count, total)}%)\n")
        f.write("\n")

        f.write("-" * 70 + "\n")
        f.write("-- BREAKDOWN BY INSTANCE SIZE --\n\n")
        header = (f"{'Size':>8} | {'N':>5} | {'Clean%':>7} | {'Reparse%':>9} | "
                  f"{'Unparse%':>9} | {'StructValid%':>13} | {'GenT_mean':>10} | {'GenT_max':>9}")
        f.write(header + "\n")
        f.write("-" * len(header) + "\n")
        for row in size_rows:
            size_str = f"{row['num_jobs']}x{row['num_machines']}"
            f.write(
                f"{size_str:>8} | {row['n_instances']:>5} | {row['clean_format_rate_pct']!s:>7} | "
                f"{row['reparse_rate_pct']!s:>9} | {row['unparseable_rate_pct']!s:>9} | "
                f"{row['structural_validity_rate_pct']!s:>13} | {row['gen_time_mean_sec']!s:>10} | "
                f"{row['gen_time_max_sec']!s:>9}\n"
            )
        f.write("\n")
        f.write("NOTE: no gap% or makespan figures are included here. Structural validity\n")
        f.write("only confirms each machine row is a permutation of the jobs -- it does NOT\n")
        f.write("guarantee the matrix is cycle-free across machines. Gap% requires solving\n")
        f.write("the structurally valid subset via MiniZinc/CP-SAT (k=0 feasibility check),\n")
        f.write("which is the next planned stage, not included in this report.\n")

    print(f"Wrote {REPORT_TXT}, {BY_SIZE_CSV}, {OVERALL_CSV}")
    print("\n--- Quick preview of overall numbers ---")
    for k, v in overall.items():
        print(f"{k}: {v}")
    print("\n--- Invalid-reason breakdown ---")
    for bucket, count in sorted(reason_counter.items(), key=lambda x: -x[1]):
        print(f"{bucket}: {count} ({pct(count, n_invalid)}% of invalid)")


if __name__ == "__main__":
    main()
