#!/bin/bash
#
# Benchmark solving -- SLURM array job, one task per instance family.
# 3 tasks: ta (80 instances), dmu (80 instances), swv (20 instances)
#
# Per-instance timeout: 9 hours (32400s)
# Worst case: ~80 * 9h = 720h, but instances run sequentially and most
# closed instances finish in minutes -- realistic time is 3-5 days per task.
# Wall time set to 9 days to be safe.
#
# Submit:   sbatch submit_benchmarks.sh
# Monitor:  squeue --me && tail -f logs/bench_<jobid>_<taskid>.out
# Merge:    cat benchmarks/results_*.jsonl > benchmarks/results_all.jsonl

#SBATCH --job-name=jsp-benchmarks
#SBATCH --partition=cpuamd
#SBATCH --account=laas_member
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=16G
#SBATCH --time=9-00:00:00
#SBATCH --output=logs/bench_%A_%a.out
#SBATCH --error=logs/bench_%A_%a.err
#SBATCH --array=0-2
#SBATCH --mail-type=FAIL,END

FAMILIES=("ta" "dmu" "swv")
FAMILY=${FAMILIES[$SLURM_ARRAY_TASK_ID]}

SCRIPT_DIR=/home/$USER/jsp_records
BENCH_DIR=$SCRIPT_DIR/benchmarks
INDEX=$BENCH_DIR/index.json
OUTPUT=$BENCH_DIR/results_${FAMILY}.jsonl

mkdir -p "$SCRIPT_DIR/logs"

# Environment -- load in this order so PATH is correct for the Python subprocess
source ~/.bashrc
source ~/ft_env/bin/activate

# Explicit PATH addition AFTER bashrc so it isn't overwritten
export PATH="/home/$USER/minizinc/bin:$PATH"

cd "$SCRIPT_DIR"

echo "======================================================"
echo " Task     : $SLURM_ARRAY_TASK_ID -- family: $FAMILY"
echo " Node     : $SLURMD_NODENAME"
echo " CPUs     : $SLURM_CPUS_PER_TASK"
echo " Started  : $(date)"
echo " MiniZinc : $(which minizinc) -- $(minizinc --version 2>&1 | head -1)"
echo "======================================================"

# The Python script auto-detects cp-sat vs chuffed via --solvers check
python3 solve_benchmarks.py \
    --index    "$INDEX"   \
    --output   "$OUTPUT"  \
    --family   "$FAMILY"  \
    --solver   cpsat      \
    --timeout  32400      \
    --threads  16

echo "Finished: $(date)"
