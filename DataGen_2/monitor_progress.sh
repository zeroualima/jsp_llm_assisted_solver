#!/bin/bash
#
# monitor_progress.sh — run this ANY TIME, even while the array job is
# still running, to see how many tasks have finished and what they found.
# Tasks still running simply won't have a .stats.json yet -- that's normal.
#
# Usage: bash monitor_progress.sh

OUTPUT_DIR=/home/$USER/jsp_dataset_v2/parts
NUM_TASKS=42

echo "Job status (squeue):"
squeue -u $USER --name=jsp-dataset-v2
echo ""

done_count=0
total_records=0
total_failed_instances=0
total_p1_no_sol=0
total_p1_timeout=0
total_p2_no_sol=0
total_dupes=0

printf "%-6s %-8s %-12s %-10s %-10s\n" "task" "size" "records" "failed" "dupes_skip"
for i in $(seq 0 $((NUM_TASKS - 1))); do
    f="$OUTPUT_DIR/task_${i}.jsonl.stats.json"
    if [ -f "$f" ]; then
        done_count=$((done_count + 1))
        nj=$(python3 -c "import json; print(json.load(open('$f'))['nj'])")
        nm=$(python3 -c "import json; print(json.load(open('$f'))['nm'])")
        rec=$(python3 -c "import json; print(json.load(open('$f'))['records_written'])")
        fail=$(python3 -c "import json; print(json.load(open('$f'))['instances_failed_entirely'])")
        dupe=$(python3 -c "import json; print(json.load(open('$f'))['duplicate_sequences_skipped'])")
        p1ns=$(python3 -c "import json; print(json.load(open('$f'))['phase1_no_solution'])")
        p1to=$(python3 -c "import json; print(json.load(open('$f'))['phase1_timed_out'])")
        p2ns=$(python3 -c "import json; print(json.load(open('$f'))['phase2_no_solution'])")

        printf "%-6s %-8s %-12s %-10s %-10s\n" "$i" "${nj}x${nm}" "$rec" "$fail" "$dupe"

        total_records=$((total_records + rec))
        total_failed_instances=$((total_failed_instances + fail))
        total_p1_no_sol=$((total_p1_no_sol + p1ns))
        total_p1_timeout=$((total_p1_timeout + p1to))
        total_p2_no_sol=$((total_p2_no_sol + p2ns))
        total_dupes=$((total_dupes + dupe))
    fi
done

echo ""
echo "======================================================"
echo " Tasks completed: $done_count / $NUM_TASKS"
echo " Total records so far: $total_records"
echo " Instances that failed entirely: $total_failed_instances"
echo " Phase-1 no-solution count: $total_p1_no_sol"
echo " Phase-1 timeout (best-found, not proven) count: $total_p1_timeout"
echo " Phase-2 no-solution count: $total_p2_no_sol"
echo " Duplicate sequences skipped (dedup): $total_dupes"
echo "======================================================"
echo ""
echo "If records are heavily skewed toward duplicate sequences for a"
echo "given size, that size's instances are saturating quickly --"
echo "consider raising num-instances or MAX_SOLUTIONS_PER_INSTANCE for it."