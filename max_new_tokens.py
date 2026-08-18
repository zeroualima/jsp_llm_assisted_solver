import numpy as np
import json
from transformers import AutoTokenizer

MODEL_ID = "meta-llama/Meta-Llama-3.1-8B-Instruct"
tockenizer = AutoTokenizer.from_pretrained(MODEL_ID)
tockenizer.pad_token = tockenizer.eos_token

lengths = []
with open("/home/mazerouali/Desktop/fine_tuning_v4_backup/fine_tuning_data_v4/train_ft_op.jsonl") as f :
    for line in f :
        rec = json.loads(line)
        lengths.append(len(tockenizer(rec["completion"])("input_ids")))
 
print("max:", max(lengths), "p99:", np.percentile(lengths, 99), "mean:", np.mean(lengths))