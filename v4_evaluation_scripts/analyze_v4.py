"""
analyze_v4.py

Reads the reparsed V4 evaluation results (v4_eval_results_reparsed.jsonl) and
produces:
  - v4_report.txt   : human-readable summary report (paste into email / read directly)
  - v4_by_size.csv   : per-instance-size table (paste into LaTeX via pandas.to_latex or csv2latex)
  - v4_overall.csv   : single-row overall summary table

Run locally on desktop, no cluster/GPU needed.
"""

import json
import csv
from collections import defaultdict
import statistics as st

INPUT = "../v4_eval_results_reparsed.jsonl"
REPORT_TXT = "../v4_report.txt"
BY_SIZE_CSV = "../v4_by_size.csv"
OVERALL_CSV = "../v4_overall.csv"


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

    overall = {
        "n_instances": total,
        "n_clean_format": sum(1 for r in recs if r.get("response_format") == "clean"),
        "n_needed_reparse": sum(1 for r in recs if r.get("response_format") == "needed_reparse"),
        "n_no_array_extractable": sum(1 for r in recs if r["full"]["reason"] == "No array could be extracted at all."),
        "n_feasible_full": sum(1 for r in recs if r["full"]["feasible"]),
        "n_infeasible_full": sum(1 for r in recs if not r["full"]["feasible"]),
        "n_feasible_truncated_only": sum(
            1 for r in recs
            if not r["full"]["feasible"] and r.get("truncated") and r["truncated"].get("feasible")
        ),
        "gen_time_mean_sec": safe_mean([r["generation_time_sec"] for r in recs]),
        "gen_time_median_sec": safe_median([r["generation_time_sec"] for r in recs]),
        "gen_time_max_sec": max((r["generation_time_sec"] for r in recs), default=None),
    }
    overall["feasibility_rate_pct"] = pct(overall["n_feasible_full"], total)
    overall["clean_format_rate_pct"] = pct(overall["n_clean_format"], total)
    overall["reparse_needed_rate_pct"] = pct(overall["n_needed_reparse"], total)

    feasible_gaps = [r["gap_percent_full"] for r in recs if r["full"]["feasible"] and r.get("gap_percent_full") is not None]
    overall["gap_pct_mean_feasible_only"] = safe_mean(feasible_gaps)
    overall["gap_pct_median_feasible_only"] = safe_median(feasible_gaps)
    overall["gap_pct_min_feasible_only"] = round(min(feasible_gaps), 3) if feasible_gaps else None
    overall["gap_pct_max_feasible_only"] = round(max(feasible_gaps), 3) if feasible_gaps else None

    # gap over ALL instances, penalizing infeasible ones as undefined/excluded is one view,
    # but we also report what fraction of the full set the gap numbers actually represent
    overall["gap_coverage_pct"] = pct(len(feasible_gaps), total)

    # --- Per-size breakdown ---
    size_rows = []
    for (nj, nm), group in sorted(by_size.items()):
        n = len(group)
        n_feasible = sum(1 for r in group if r["full"]["feasible"])
        n_clean = sum(1 for r in group if r.get("response_format") == "clean")
        gaps = [r["gap_percent_full"] for r in group if r["full"]["feasible"] and r.get("gap_percent_full") is not None]
        gen_times = [r["generation_time_sec"] for r in group]

        n_infeasible_length = sum(
            1 for r in group if not r["full"]["feasible"] and r["full"]["reason"] and r["full"]["reason"].startswith("Invalid length")
        )
        n_infeasible_no_array = sum(
            1 for r in group if r["full"]["reason"] == "No array could be extracted at all."
        )

        size_rows.append({
            "num_jobs": nj,
            "num_machines": nm,
            "n_instances": n,
            "n_feasible": n_feasible,
            "feasibility_rate_pct": pct(n_feasible, n),
            "n_clean_format": n_clean,
            "clean_format_rate_pct": pct(n_clean, n),
            "n_infeasible_wrong_length": n_infeasible_length,
            "n_infeasible_no_array_found": n_infeasible_no_array,
            "gen_time_mean_sec": safe_mean(gen_times),
            "gen_time_max_sec": round(max(gen_times), 2) if gen_times else None,
            "gap_pct_mean": safe_mean(gaps),
            "gap_pct_median": safe_median(gaps),
            "gap_pct_min": round(min(gaps), 3) if gaps else None,
            "gap_pct_max": round(max(gaps), 3) if gaps else None,
            "n_with_gap_data": len(gaps),
        })

    # --- Key/format distribution (schema adherence) ---
    key_counts = defaultdict(int)
    for r in recs:
        key_counts[r.get("detected_key")] += 1

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
        f.write("V4 FINE-TUNED MODEL EVALUATION REPORT\n")
        f.write("Bierwirth operation-array warm-start, val_1950 instance set\n")
        f.write("=" * 70 + "\n\n")

        f.write("-- OVERALL SUMMARY --\n\n")
        f.write(f"Total instances evaluated:              {overall['n_instances']}\n")
        f.write(f"Clean-schema responses (op_array, no leading junk): {overall['n_clean_format']} ({overall['clean_format_rate_pct']}%)\n")
        f.write(f"Responses needing permissive reparse:   {overall['n_needed_reparse']} ({overall['reparse_needed_rate_pct']}%)\n")
        f.write(f"Responses with no array extractable at all: {overall['n_no_array_extractable']}\n\n")

        f.write(f"Feasible (valid schedule) responses:    {overall['n_feasible_full']} ({overall['feasibility_rate_pct']}%)\n")
        f.write(f"Infeasible responses:                   {overall['n_infeasible_full']}\n")
        f.write(f"  of which recoverable via truncation to expected length: {overall['n_feasible_truncated_only']}\n\n")

        f.write(f"Generation time (sec) - mean: {overall['gen_time_mean_sec']}, median: {overall['gen_time_median_sec']}, max: {overall['gen_time_max_sec']}\n\n")

        f.write(f"Gap %% vs best known makespan (feasible instances only, n={len(feasible_gaps)}, {overall['gap_coverage_pct']}% of total):\n")
        f.write(f"  mean:   {overall['gap_pct_mean_feasible_only']}%\n")
        f.write(f"  median: {overall['gap_pct_median_feasible_only']}%\n")
        f.write(f"  min:    {overall['gap_pct_min_feasible_only']}%\n")
        f.write(f"  max:    {overall['gap_pct_max_feasible_only']}%\n\n")

        f.write("NOTE: gap%% figures above only cover the feasible subset. They are NOT\n")
        f.write("representative of overall model reliability by themselves -- always report\n")
        f.write("them alongside the feasibility rate above, since a high gap%% quality on a\n")
        f.write("small feasible subset can look misleadingly good in isolation.\n\n")

        f.write("-" * 70 + "\n")
        f.write("-- SCHEMA KEY ADHERENCE (what JSON key did the model actually emit) --\n\n")
        for key, count in sorted(key_counts.items(), key=lambda x: -x[1]):
            label = key if key else "(no key detected)"
            f.write(f"  {label:20s}: {count:5d}  ({pct(count, total)}%)\n")
        f.write("\n")

        f.write("-" * 70 + "\n")
        f.write("-- BREAKDOWN BY INSTANCE SIZE --\n\n")
        header = (f"{'Size':>8} | {'N':>5} | {'Feasible':>9} | {'Feas.%':>7} | "
                  f"{'Clean%':>7} | {'GenT_mean':>10} | {'GenT_max':>9} | "
                  f"{'Gap_mean%':>10} | {'Gap_med%':>9} | {'N_gap':>6}")
        f.write(header + "\n")
        f.write("-" * len(header) + "\n")
        for row in size_rows:
            size_str = f"{row['num_jobs']}x{row['num_machines']}"
            f.write(
                f"{size_str:>8} | {row['n_instances']:>5} | {row['n_feasible']:>9} | "
                f"{row['feasibility_rate_pct']!s:>7} | {row['clean_format_rate_pct']!s:>7} | "
                f"{row['gen_time_mean_sec']!s:>10} | {row['gen_time_max_sec']!s:>9} | "
                f"{row['gap_pct_mean']!s:>10} | {row['gap_pct_median']!s:>9} | {row['n_with_gap_data']!s:>6}\n"
            )
        f.write("\n")

        f.write("-" * 70 + "\n")
        f.write("-- FAILURE MODE BREAKDOWN BY SIZE (infeasible responses only) --\n\n")
        header2 = f"{'Size':>8} | {'Wrong length (degenerate)':>26} | {'No array/key found':>20}"
        f.write(header2 + "\n")
        f.write("-" * len(header2) + "\n")
        for row in size_rows:
            size_str = f"{row['num_jobs']}x{row['num_machines']}"
            f.write(f"{size_str:>8} | {row['n_infeasible_wrong_length']:>26} | {row['n_infeasible_no_array_found']:>20}\n")

    print(f"Wrote {REPORT_TXT}, {BY_SIZE_CSV}, {OVERALL_CSV}")
    print("\n--- Quick preview of overall numbers ---")
    for k, v in overall.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
