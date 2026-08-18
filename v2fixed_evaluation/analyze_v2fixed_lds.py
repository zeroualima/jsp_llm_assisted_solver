"""
analyze_v2fixed_lds.py

Reads v2fixed_eval_results_solved.jsonl and produces:
  - v2fixed_lds_report.txt   : human-readable summary report
  - v2fixed_lds_by_size.csv  : per-instance-size table
  - v2fixed_lds_overall.csv  : single-row overall summary table

Covers only the LDS/solver-derived variables (k, cycle_free, lds_status,
makespan, gap_percent, lds_solve_time_sec). Structural validity / format
numbers are already covered by analyze_v2fixed.py -- this script picks up
where that one left off, restricted to the structurally valid subset that
was actually run through the solver.

Run locally on desktop, no cluster/GPU needed.
"""

import json
import csv
from collections import defaultdict
import statistics as st

INPUT = "/home/mazerouali/Desktop/fine_tuning_v2_fixed_backup/v2fixed_evaluation/v2fixed_eval_results_solved.jsonl"
REPORT_TXT = "/home/mazerouali/Desktop/fine_tuning_v2_fixed_backup/v2fixed_evaluation/v2fixed_lds_report.txt"
BY_SIZE_CSV = "/home/mazerouali/Desktop/fine_tuning_v2_fixed_backup/v2fixed_evaluation/v2fixed_lds_by_size.csv"
OVERALL_CSV = "/home/mazerouali/Desktop/fine_tuning_v2_fixed_backup/v2fixed_evaluation/v2fixed_lds_overall.csv"


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

    # Universe of instances actually sent to the solver (structurally valid)
    solved_pool = [r for r in recs if r.get("structural_validity")]
    n_pool = len(solved_pool)

    by_size_all = defaultdict(list)
    for r in recs:
        by_size_all[size_key(r)].append(r)

    by_size_pool = defaultdict(list)
    for r in solved_pool:
        by_size_pool[size_key(r)].append(r)

    # --- lds_status distribution, over the structurally valid pool ---
    n_lds_solved = sum(1 for r in solved_pool if r["lds_status"] == "solved")
    n_k_cap_exceeded = sum(1 for r in solved_pool if r["lds_status"] == "k_cap_exceeded")
    n_timeout_undetermined = sum(1 for r in solved_pool if r["lds_status"] == "timeout_undetermined")

    # --- k / cycle-free stats, over solved-only subset ---
    solved_recs = [r for r in solved_pool if r["lds_status"] == "solved"]
    ks = [r["k"] for r in solved_recs]
    n_cycle_free = sum(1 for r in solved_recs if r["cycle_free"])
    n_needed_discrepancies = sum(1 for r in solved_recs if not r["cycle_free"])

    # --- gap% stats, over solved-only subset (makespan always set there) ---
    gaps = [r["gap_percent"] for r in solved_recs if r["gap_percent"] is not None]

    # --- solve time stats, over the full structurally valid pool
    # (k_cap_exceeded/timeout instances still consumed solve time) ---
    solve_times = [r["lds_solve_time_sec"] for r in solved_pool if r.get("lds_solve_time_sec") is not None]

    overall = {
        "n_total_instances": total,
        "n_structurally_valid_sent_to_solver": n_pool,
        "structurally_valid_rate_pct": pct(n_pool, total),
        "n_lds_solved": n_lds_solved,
        "lds_solved_rate_pct_of_pool": pct(n_lds_solved, n_pool),
        "n_k_cap_exceeded": n_k_cap_exceeded,
        "k_cap_exceeded_rate_pct_of_pool": pct(n_k_cap_exceeded, n_pool),
        "n_timeout_undetermined": n_timeout_undetermined,
        "timeout_undetermined_rate_pct_of_pool": pct(n_timeout_undetermined, n_pool),
        "n_cycle_free_k0": n_cycle_free,
        "cycle_free_rate_pct_of_solved": pct(n_cycle_free, n_lds_solved),
        "cycle_free_rate_pct_of_total": pct(n_cycle_free, total),
        "n_needed_discrepancies_k_gt_0": n_needed_discrepancies,
        "k_mean": safe_mean(ks),
        "k_median": safe_median(ks),
        "k_max": max(ks) if ks else None,
        "gap_pct_mean": safe_mean(gaps),
        "gap_pct_median": safe_median(gaps),
        "gap_pct_min": round(min(gaps), 3) if gaps else None,
        "gap_pct_max": round(max(gaps), 3) if gaps else None,
        "gap_coverage_pct_of_total": pct(len(gaps), total),
        "lds_solve_time_mean_sec": safe_mean(solve_times),
        "lds_solve_time_median_sec": safe_median(solve_times),
        "lds_solve_time_max_sec": max(solve_times) if solve_times else None,
    }

    # --- Per-size breakdown ---
    size_rows = []
    all_sizes = sorted(set(list(by_size_all.keys())))
    for (nj, nm) in all_sizes:
        group_all = by_size_all[(nj, nm)]
        group_pool = by_size_pool.get((nj, nm), [])
        n_total_size = len(group_all)
        n_pool_size = len(group_pool)

        group_solved = [r for r in group_pool if r["lds_status"] == "solved"]
        n_solved_size = len(group_solved)
        n_cap_size = sum(1 for r in group_pool if r["lds_status"] == "k_cap_exceeded")
        n_to_size = sum(1 for r in group_pool if r["lds_status"] == "timeout_undetermined")

        ks_size = [r["k"] for r in group_solved]
        n_cyclefree_size = sum(1 for r in group_solved if r["cycle_free"])
        gaps_size = [r["gap_percent"] for r in group_solved if r["gap_percent"] is not None]
        solve_times_size = [r["lds_solve_time_sec"] for r in group_pool if r.get("lds_solve_time_sec") is not None]

        size_rows.append({
            "num_jobs": nj,
            "num_machines": nm,
            "n_total": n_total_size,
            "n_sent_to_solver": n_pool_size,
            "n_lds_solved": n_solved_size,
            "lds_solved_rate_pct": pct(n_solved_size, n_pool_size),
            "n_k_cap_exceeded": n_cap_size,
            "n_timeout_undetermined": n_to_size,
            "n_cycle_free_k0": n_cyclefree_size,
            "cycle_free_rate_pct_of_solved": pct(n_cyclefree_size, n_solved_size),
            "k_mean": safe_mean(ks_size),
            "k_median": safe_median(ks_size),
            "k_max": max(ks_size) if ks_size else None,
            "gap_pct_mean": safe_mean(gaps_size),
            "gap_pct_median": safe_median(gaps_size),
            "n_with_gap_data": len(gaps_size),
            "solve_time_mean_sec": safe_mean(solve_times_size),
            "solve_time_max_sec": max(solve_times_size) if solve_times_size else None,
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
        f.write("V2-FIXED LDS RESOLUTION REPORT\n")
        f.write("Cycle-freeness, k, makespan and gap%, val_1950 instance set\n")
        f.write("=" * 70 + "\n\n")

        f.write("-- SCOPE --\n\n")
        f.write(f"Total instances in validation set:                {overall['n_total_instances']}\n")
        f.write(f"Structurally valid, sent to the solver:           {overall['n_structurally_valid_sent_to_solver']} ({overall['structurally_valid_rate_pct']}%)\n\n")
        f.write("All figures below are computed over this structurally valid pool\n")
        f.write("unless stated otherwise as a percentage of the full 1950-instance set.\n\n")

        f.write("-- LDS SEARCH OUTCOME --\n\n")
        f.write(f"  Solved (minimal k found):      {overall['n_lds_solved']} ({overall['lds_solved_rate_pct_of_pool']}% of pool)\n")
        f.write(f"  k_cap exceeded (never solved):  {overall['n_k_cap_exceeded']} ({overall['k_cap_exceeded_rate_pct_of_pool']}% of pool)\n")
        f.write(f"  Timeout, undetermined:          {overall['n_timeout_undetermined']} ({overall['timeout_undetermined_rate_pct_of_pool']}% of pool)\n\n")

        f.write("-- CYCLE-FREENESS AND DISCREPANCIES (over solved subset) --\n\n")
        f.write(f"  Cycle-free at k=0:               {overall['n_cycle_free_k0']} ({overall['cycle_free_rate_pct_of_solved']}% of solved, {overall['cycle_free_rate_pct_of_total']}% of all 1950 instances)\n")
        f.write(f"  Needed discrepancies (k>0):       {overall['n_needed_discrepancies_k_gt_0']}\n")
        f.write(f"  k -- mean: {overall['k_mean']}, median: {overall['k_median']}, max: {overall['k_max']}\n\n")

        f.write("-- GAP TO BEST KNOWN MAKESPAN (over solved subset) --\n\n")
        f.write(f"  Coverage: {len(gaps)} instances ({overall['gap_coverage_pct_of_total']}% of all 1950 instances)\n")
        f.write(f"  mean:   {overall['gap_pct_mean']}%\n")
        f.write(f"  median: {overall['gap_pct_median']}%\n")
        f.write(f"  min:    {overall['gap_pct_min']}%\n")
        f.write(f"  max:    {overall['gap_pct_max']}%\n\n")
        f.write("NOTE: gap% here reflects the makespan found by the solver AFTER\n")
        f.write("resolving k discrepancies -- not the LLM's raw proposal. It should be\n")
        f.write("read as 'quality of the LLM-guided search result', not 'quality of the\n")
        f.write("LLM's own answer' (unlike V4's gap%, computed on a direct decode).\n\n")

        f.write(f"LDS solve time (sec) -- mean: {overall['lds_solve_time_mean_sec']}, "
                f"median: {overall['lds_solve_time_median_sec']}, max: {overall['lds_solve_time_max_sec']}\n\n")

        f.write("-" * 70 + "\n")
        f.write("-- BREAKDOWN BY INSTANCE SIZE --\n\n")
        header = (f"{'Size':>8} | {'N_tot':>6} | {'N_pool':>6} | {'Solved%':>8} | "
                  f"{'CycFree%':>9} | {'k_mean':>7} | {'k_max':>6} | "
                  f"{'Gap_mean%':>10} | {'N_gap':>6} | {'SolveT_mean':>11}")
        f.write(header + "\n")
        f.write("-" * len(header) + "\n")
        for row in size_rows:
            size_str = f"{row['num_jobs']}x{row['num_machines']}"
            f.write(
                f"{size_str:>8} | {row['n_total']:>6} | {row['n_sent_to_solver']:>6} | "
                f"{row['lds_solved_rate_pct']!s:>8} | {row['cycle_free_rate_pct_of_solved']!s:>9} | "
                f"{row['k_mean']!s:>7} | {row['k_max']!s:>6} | "
                f"{row['gap_pct_mean']!s:>10} | {row['n_with_gap_data']!s:>6} | "
                f"{row['solve_time_mean_sec']!s:>11}\n"
            )
        f.write("\n")
        f.write("NOTE: N_pool is the number of structurally valid instances at this size\n")
        f.write("(from analyze_v2fixed.py); 'Solved%' is the share of N_pool for which the\n")
        f.write("solver found a minimal k within the k_cap; k_mean/k_max/Gap/SolveT are\n")
        f.write("computed only over the solved subset at this size.\n")

    print(f"Wrote {REPORT_TXT}, {BY_SIZE_CSV}, {OVERALL_CSV}")
    print("\n--- Quick preview of overall numbers ---")
    for k, v in overall.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
