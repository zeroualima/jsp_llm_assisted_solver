#!/bin/bash
#
# merge_dataset.sh — run this AFTER all SLURM array tasks have completed.
#
# Usage:
#   bash merge_dataset.sh
#
# What it does:
#   1. Checks all 39 task output files exist
#   2. Reports per-task record counts
#   3. Concatenates everything into dataset.jsonl
#   4. Prints a final summary

OUTPUT_DIR=/home/$USER/jsp_dataset/parts
FINAL_FILE=/home/$USER/jsp_dataset/dataset.jsonl
NUM_TASKS=39

echo "Checking part files..."
missing=0
for i in $(seq 0 $((NUM_TASKS - 1))); do
    f="$OUTPUT_DIR/task_${i}.jsonl"
    if [ ! -f "$f" ]; then
        echo "  MISSING: $f"
        missing=$((missing + 1))
    else
        count=$(wc -l < "$f")
        echo "  task_${i}: $count records"
    fi
done

if [ $missing -gt 0 ]; then
    echo ""
    echo "WARNING: $missing task file(s) missing. Re-run failed tasks before merging."
    echo "To resubmit specific tasks (e.g. 3 and 17):"
    echo "  sbatch --array=3,17 submit_dataset.sh"
    exit 1
fi

echo ""
echo "Merging into $FINAL_FILE ..."
cat "$OUTPUT_DIR"/task_*.jsonl > "$FINAL_FILE"

total=$(wc -l < "$FINAL_FILE")
echo "Done. Total records in dataset.jsonl: $total"
