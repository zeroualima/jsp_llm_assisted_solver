import json
from collections import Counter

counts = Counter()

with open("/home/mazerouali/Desktop/Backup/train.jsonl") as f:
    for line in f:
        x = json.loads(line)["instance"]
        counts[(x["num_jobs"], x["num_machines"])] += 1

for (jobs, machines), n in sorted(counts.items()):
    print(f"{jobs} jobs, {machines} machines: {n}")