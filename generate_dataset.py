import os
import json
import random
import subprocess

NUM_INSTANCES_PER_COMBINATION = 1 # 500  # Target scale per explicit combination
DURATION_RANGES = [5] #, 20, 100]
MATRIX_SIZES = [[5, 5]] #, [6, 6], [8, 8], [10, 10], [10, 15], [10, 20], [15, 15], [20, 15], [20, 20]]
MODEL_PATH = "jsp/model.mzn"
DATASET_FILE = "dataset.jsonl"
TIMEOUT_MS = 60000                  # 1 minute per instance

def generate_random_instance(num_jobs, num_machines, duration_range):
    """Generates random Job Shop data matching the matrix format."""
    durations = []
    machines = []
    
    for j in range(num_jobs):
        dur_row = [random.randint(1, duration_range) for _ in range(num_machines)]
        
        mach_row = list(range(0, num_machines))
        random.shuffle(mach_row)
        
        durations.append(dur_row)
        machines.append(mach_row)
        
    return {
        "n_jobs": num_jobs,
        "n_machines": num_machines,
        "job_task_duration": durations,
        "job_task_machine": machines
    }

def run_pipeline():
    global_instance_idx = 0
    
    total_batches = len(MATRIX_SIZES) * len(DURATION_RANGES)
    print(f"Starting dataset compilation across {total_batches} targeted configurations...")

    for nj, nm in MATRIX_SIZES:
        for dur_max in DURATION_RANGES:
            
            print(f"\n==================================================")
            print(f" Running Batch: {nj} Jobs x {nm} Machines | Max Duration: {dur_max}")
            print(f"==================================================")

            for local_idx in range(NUM_INSTANCES_PER_COMBINATION):
                print(f"Generating instance {local_idx+1}/{NUM_INSTANCES_PER_COMBINATION}...")
                
                instance = generate_random_instance(nj, nm, dur_max)

                temp_json = "jsp/temp_data.json"
                with open(temp_json, "w") as f:
                    json.dump(instance, f)

                cmd = [
                    "minizinc", "--solver", "Chuffed",
                    "--all-solutions", "--statistics",
                    "-t", str(TIMEOUT_MS),
                    "--output-mode", "json", "--json-stream",
                    MODEL_PATH, temp_json
                ]

                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    print(f"MiniZinc failed with exit code {result.returncode}!")
                    print(f"Error details (stderr): {result.stderr}")
                    print(f"Compiler details (stdout): {result.stdout}")
                    continue

                solution_list = []
                final_status = "UNKNOWN"
                solver_stats = {}
                
                for line in result.stdout.splitlines():
                    if not line.strip(): continue
                    try:
                        entry = json.loads(line)
                        if entry["type"] == "solution":
                            solution_list.append(entry["output"]["json"])
                        elif entry["type"] == "status":
                            final_status = entry["status"]
                        elif entry["type"] == "statistics": 
                            solver_stats.update(entry["statistics"])
                    except json.JSONDecodeError:
                        continue

                solver_proved_optimality = (final_status == "OPTIMAL_SOLUTION")
                
                best_makespan_found = solution_list[-1]["C"] if solution_list else -1
                
                if solver_proved_optimality:
                    optimal_makespan = best_makespan_found
                else:
                    optimal_makespan = -1 

                with open(DATASET_FILE, "a") as out_file:
                    for i, sol in enumerate(solution_list):
                        is_last = (i == len(solution_list) - 1)
                        current_makespan = sol["C"]
                        
                        if solver_proved_optimality:
                            gap_percent = ((current_makespan - optimal_makespan) * 100.0) / optimal_makespan
                        else:
                            gap_percent = -1.0 
                        
                        record = {
                            "instance": {
                                "source": "synthetic_generator",
                                "id": f"synth_{global_instance_idx:05d}",
                                "num_jobs": instance["n_jobs"],
                                "num_machines": instance["n_machines"],
                                "durations": instance["job_task_duration"],
                                "machines": instance["job_task_machine"]
                            },
                            "solution": {
                                "starts": sol["x"],
                                "makespan": current_makespan,
                                "optimal_makespan": optimal_makespan,
                                "gap_percent": round(gap_percent, 2),
                                "is_optimal": True if (is_last and solver_proved_optimality) else False
                            },
                            "solver_stats": {
                                "nodes": solver_stats.get("nodes", 0),
                                "failures": solver_stats.get("failures", 0),
                                "solve_time": solver_stats.get("solveTime", 0.0)
                            }
                        }
                        out_file.write(json.dumps(record) + "\n")
                
                global_instance_idx += 1

    if os.path.exists(temp_json):
        os.remove(temp_json)
        
    print("\nDataset generation complete!")

if __name__ == "__main__":
    run_pipeline()