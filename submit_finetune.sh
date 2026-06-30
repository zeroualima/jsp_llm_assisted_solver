#!/bin/bash
#SBATCH --nodelist=dolcino
#SBATCH --job-name=jsp-finetune
#SBATCH --partition=gpu
#SBATCH --account=laas_member
#SBATCH --gres=gpu:rtx_a6000:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=48:00:00
#SBATCH --output=logs/ft_%j.out
#SBATCH --error=logs/ft_%j.err
#SBATCH --mail-type=FAIL,END

source ~/.bashrc
source ~/ft_env/bin/activate

cd ~/jsp_records
python3 finetune.py
