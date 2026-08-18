import json

input_file = "/home/mazerouali/Desktop/Backup/val.jsonl"
output_file = "/home/mazerouali/Desktop/val_1950.jsonl"

unique_instances = {}

with open(input_file, 'r') as infile:
    for line in infile:
        if not line.strip():
            continue
            
        record = json.loads(line)
        inst = record["instance"]
        sol = record["solution"]
        
        inst_id = inst["id"]
        current_makespan = sol["makespan"]
        current_is_optimal = sol["is_optimal"]
        
        if inst_id not in unique_instances:
            unique_instances[inst_id] = {
                "id": inst_id,
                "num_jobs": inst["num_jobs"],
                "num_machines": inst["num_machines"],
                "durations": inst["durations"],
                "machines": inst["machines"],
                "is_optimal": current_is_optimal,
                "best_makespan": current_makespan
            }
        else:
            if current_makespan < unique_instances[inst_id]["best_makespan"]:
                unique_instances[inst_id]["best_makespan"] = current_makespan
            
            if current_is_optimal:
                unique_instances[inst_id]["is_optimal"] = True

print(f"Processed {len(unique_instances)} unique instances.")

with open(output_file, 'w') as outfile:
    for inst_data in unique_instances.values():
        outfile.write(json.dumps(inst_data) + '\n')

print(f"Successfully saved clean dataset to {output_file}")