#!/bin/bash
#
# JSP Dataset Generation — SLURM array job
#
# 39 tasks: one per (nj, nm, dur_max) combination.
# Each task runs NUM_INSTANCES MiniZinc solves in parallel (WORKERS at a time).
#
# Submit with:  sbatch submit_dataset.sh
# Monitor with: squeue -u $USER
# Cancel all:   scancel --name=jsp-dataset
#
# After all tasks finish, merge outputs:
#   cat /home/$USER/jsp_dataset/parts/task_*.jsonl > /home/$USER/jsp_dataset/dataset.jsonl

#SBATCH --job-name=jsp-dataset
#SBATCH --partition=roc
#SBATCH --nodelist=askew
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16          # one CPU per parallel MiniZinc process
#SBATCH --mem=32G                   # ~2 GB per worker is generous for Chuffed
#SBATCH --time=02:30:00             # 500 inst / 16 workers * 15 min + buffer
#SBATCH --output=logs/jsp_%A_%a.out
#SBATCH --error=logs/jsp_%A_%a.err
#SBATCH --array=0-38       # 39 tasks (13 sizes * 3 duration ranges)
#SBATCH --mail-type=FAIL,END

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WORKERS=16
NUM_INSTANCES=500
BASE_SEED=12345
SCRIPT_DIR=/home/$USER/jsp_records
OUTPUT_DIR=/home/$USER/jsp_dataset/parts
SCRATCH_DIR=/scratch/$USER/jsp_tmp      # fast local I/O during solve

# ---------------------------------------------------------------------------
# Combination table: maps SLURM_ARRAY_TASK_ID (0..38) to (nj, nm, dur_max)
# Layout: 13 matrix sizes * 3 duration ranges
#   size index  = TASK_ID / 3   (integer division)
#   dur index   = TASK_ID % 3
#
# Matrix sizes (nj, nm):
#   0:(3,3)  1:(4,4)  2:(5,5)  3:(6,6)  4:(8,6)
#   5:(8,8)  6:(10,8)  7:(10,10)  8:(12,12)
#   9:(15,12) 10:(15,12) 11:(15,15) 12:(20,15)
#
# Duration ranges: 0:10  1:50  2:100
# ---------------------------------------------------------------------------

NJ_LIST=( 3  4  5  6  8  8 10 10 12 12 15 15 20)
NM_LIST=( 3  4  5  6  6  8  8 10 10 12 12 15 15)
DUR_LIST=(10 50 100)

SIZE_IDX=$(( SLURM_ARRAY_TASK_ID / 3 ))
DUR_IDX=$(( SLURM_ARRAY_TASK_ID % 3 ))

NJ=${NJ_LIST[$SIZE_IDX]}
NM=${NM_LIST[$SIZE_IDX]}
DUR_MAX=${DUR_LIST[$DUR_IDX]}

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

mkdir -p "$OUTPUT_DIR"
mkdir -p "$SCRATCH_DIR"
mkdir -p logs

cd "$SCRIPT_DIR" || { echo "ERROR: SCRIPT_DIR not found: $SCRIPT_DIR"; exit 1; }

# Activate virtual environment (adjust path if needed)
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Fast scratch output for this task (avoid NFS contention during writes)
SCRATCH_OUTPUT="$SCRATCH_DIR/task_${SLURM_ARRAY_TASK_ID}.jsonl"
FINAL_OUTPUT="$OUTPUT_DIR/task_${SLURM_ARRAY_TASK_ID}.jsonl"

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

echo "======================================================"
echo " SLURM Task : $SLURM_ARRAY_TASK_ID"
echo " Node       : $SLURMD_NODENAME"
echo " Combination: nj=$NJ  nm=$NM  dur_max=$DUR_MAX"
echo " Workers    : $WORKERS  |  Instances: $NUM_INSTANCES"
echo " Output     : $FINAL_OUTPUT"
echo " Started    : $(date)"
echo "======================================================"

python3 generate_dataset.py \
    --nj           "$NJ"                        \
    --nm           "$NM"                        \
    --dur-max      "$DUR_MAX"                   \
    --num-instances "$NUM_INSTANCES"            \
    --workers      "$WORKERS"                   \
    --output       "$SCRATCH_OUTPUT"            \
    --seed         "$BASE_SEED"                 \
    --task-id      "$SLURM_ARRAY_TASK_ID"

EXIT_CODE=$?

# Copy result from scratch to shared home directory
if [ $EXIT_CODE -eq 0 ] && [ -f "$SCRATCH_OUTPUT" ]; then
    cp "$SCRATCH_OUTPUT" "$FINAL_OUTPUT"
    echo "Copied $SCRATCH_OUTPUT -> $FINAL_OUTPUT"
    rm "$SCRATCH_OUTPUT"
else
    echo "ERROR: Python script exited with code $EXIT_CODE or output file missing."
    exit 1
fi

echo "Finished: $(date)"
