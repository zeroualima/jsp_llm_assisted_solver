#!/bin/bash
#
# JSP Dataset Generation v2 -- SLURM array job, two-phase algorithm
#
# 42 tasks: 14 sizes x 3 duration ranges.
# Instance counts per task are WEIGHTED by size tier so the larger,
# benchmark-relevant sizes ((15,15), (20,15), (20,20)) are oversampled
# in the final dataset, both via raw instance count and because they
# naturally yield more distinct near-optimal solutions per instance.
#
# IMPORTANT: run a small subset first (e.g. --array=0-2,39-41) to sanity
# check records/instance before committing the full array -- the total
# record count below is an ESTIMATE (~129k), not a guarantee.
#
# Submit with:  sbatch submit_dataset.sh
# Dry run a few tasks first:  sbatch --array=0-2,39-41 submit_dataset.sh
# Monitor with: squeue -u $USER
# Cancel all:   scancel --name=jsp-dataset-v2

#SBATCH --job-name=jsp-dataset-v2
#SBATCH --partition=cpuamd
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=2-00:00:00        
#SBATCH --output=logs/jsp_%A_%a.out
#SBATCH --error=logs/jsp_%A_%a.err
#SBATCH --array=0-41
#SBATCH --mail-type=FAIL,END

# ---------------------------------------------------------------------------
# NOTE on --time: this is a flat budget shared across all 42 array indices.
# 2 days is generous enough that you shouldn't need an extension request,
# but if your partition enforces a hard QoS cap below 48h, this job will be
# rejected at submission -- check before submitting:
#   sacctmgr show qos format=Name,MaxWall
# If capped, split into two submissions (small/medium sizes vs. the three
# target sizes) with separate, tighter --time values instead.
# ---------------------------------------------------------------------------

WORKERS=16
BASE_SEED=12345
SCRIPT_DIR=/home/$USER/jsp_records
OUTPUT_DIR=/home/$USER/jsp_dataset_v2/parts
SCRATCH_DIR=/scratch/$USER/jsp_tmp_v2

# ---------------------------------------------------------------------------
# Combination table: 14 sizes x 3 duration ranges = 42 tasks
#   size index = TASK_ID / 3   (integer division)
#   dur index  = TASK_ID % 3
#
# Matrix sizes (nj, nm), index 0-13:
#   0:(3,3)   1:(4,4)   2:(5,5)   3:(6,6)   4:(8,6)   5:(8,8)
#   6:(10,8)  7:(10,10) 8:(12,10) 9:(12,12) 10:(15,12) 11:(15,15)
#   12:(20,15) 13:(20,20)
#
# Duration ranges: 0:10  1:50  2:100
#
# Instance counts per (size, duration) combo, weighted by tier.
# Raised back toward the original 500/combo baseline -- post-dedup yield
# per instance is uncertain until the dry run confirms it, so this errs
# toward generating more rather than less:
#   small  (idx 0-5):   500 instances/combo
#   medium (idx 6-10):  500 instances/combo
#   target (idx 11-13): 800 instances/combo  <- oversampled, benchmark sizes
# ---------------------------------------------------------------------------

NJ_LIST=( 3  4  5  6  8  8 10 10 12 12 15 15 20 20)
NM_LIST=( 3  4  5  6  6  8  8 10 10 12 12 15 15 20)
NUM_INSTANCES_LIST=(500 500 500 500 500 500 500 500 500 500 500 800 800 800)
DUR_LIST=(10 50 100)

SIZE_IDX=$(( SLURM_ARRAY_TASK_ID / 3 ))
DUR_IDX=$(( SLURM_ARRAY_TASK_ID % 3 ))

NJ=${NJ_LIST[$SIZE_IDX]}
NM=${NM_LIST[$SIZE_IDX]}
NUM_INSTANCES=${NUM_INSTANCES_LIST[$SIZE_IDX]}
DUR_MAX=${DUR_LIST[$DUR_IDX]}

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

mkdir -p "$OUTPUT_DIR"
mkdir -p "$SCRATCH_DIR"
mkdir -p logs

cd "$SCRIPT_DIR" || { echo "ERROR: SCRIPT_DIR not found: $SCRIPT_DIR"; exit 1; }

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

SCRATCH_OUTPUT="$SCRATCH_DIR/task_${SLURM_ARRAY_TASK_ID}.jsonl"
FINAL_OUTPUT="$OUTPUT_DIR/task_${SLURM_ARRAY_TASK_ID}.jsonl"

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

echo "======================================================"
echo " SLURM Task : $SLURM_ARRAY_TASK_ID"
echo " Node       : $SLURMD_NODENAME"
echo " Combination: nj=$NJ  nm=$NM  dur_max=$DUR_MAX  num_instances=$NUM_INSTANCES"
echo " Workers    : $WORKERS"
echo " Output     : $FINAL_OUTPUT"
echo " Started    : $(date)"
echo "======================================================"

python3 generate_dataset.py \
    --nj            "$NJ"             \
    --nm            "$NM"             \
    --dur-max       "$DUR_MAX"        \
    --num-instances "$NUM_INSTANCES"  \
    --workers       "$WORKERS"        \
    --output        "$SCRATCH_OUTPUT" \
    --seed          "$BASE_SEED"      \
    --task-id       "$SLURM_ARRAY_TASK_ID"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ] && [ -f "$SCRATCH_OUTPUT" ]; then
    cp "$SCRATCH_OUTPUT" "$FINAL_OUTPUT"
    cp "${SCRATCH_OUTPUT}.stats.json" "${FINAL_OUTPUT}.stats.json" 2>/dev/null
    echo "Copied $SCRATCH_OUTPUT -> $FINAL_OUTPUT (+ stats sidecar)"
    rm -f "$SCRATCH_OUTPUT" "${SCRATCH_OUTPUT}.stats.json"
else
    echo "ERROR: Python script exited with code $EXIT_CODE or output file missing."
    exit 1
fi

echo "Finished: $(date)"