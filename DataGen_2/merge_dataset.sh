#!/bin/bash
#
# merge_dataset.sh — run this AFTER all SLURM array tasks have completed.
#
# Usage:
#   bash merge_dataset.sh

OUTPUT_DIR=/home/$USER/jsp_dataset_v2/parts
FINAL_FILE=/home/$USER/jsp_dataset_v2/dataset.jsonl
NUM_TASKS=42

echo "Checking part files..."
missing=0
total_expected=0
for i in $(seq 0 $((NUM_TASKS - 1))); do
    f="$OUTPUT_DIR/task_${i}.jsonl"
    if [ ! -f "$f" ]; then
        echo "  MISSING: $f"
        missing=$((missing + 1))
    else
        count=$(wc -l < "$f")
        echo "  task_${i}: $count records"
        total_expected=$((total_expected + count))
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
echo ""
echo "If this total is well outside the 120k-160k target, adjust"
echo "NUM_INSTANCES_LIST in submit_dataset.sh and/or MAX_SOLUTIONS_PER_INSTANCE"
echo "in generate_dataset.py, then regenerate."