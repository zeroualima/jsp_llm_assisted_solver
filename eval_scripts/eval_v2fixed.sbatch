#!/bin/bash
#SBATCH --job-name=jsp-v2fixed-eval
#SBATCH --partition=gpu
#SBATCH --account=laas_member
#SBATCH --gres=gpu:1
#SBATCH --time=9-00:00:00
#SBATCH --output=logs/eval_v2fixed_%j.out
#SBATCH --error=logs/eval_v2fixed_%j.err

source ~/.bashrc
source ~/ft_env/bin/activate

cd ~/jsp_records

python eval_v2fixed.py \
    --input val_1950.jsonl \
    --output v2fixed_eval_results.jsonl \
    --max_new_tokens 2000
