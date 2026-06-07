import os
import json
import random
import subprocess

# Configuration
NUM_INSTANCES_PER_COMBINATION = 500
DURATION_RANGE = [5, 20, 100]
NUM_JOBS = [5, 8, 10, 12, 15]
NUM_MACHINES = [5, 8, 10, 12, 15]
MODEL_PATH = "jsp/model.mzn"
DATASET_FILE = "dataset.jsonl"
TIMEOUT_MS = 60000  # 1 minute per instance

def generate_random_instance(num_jobs, num_machines, duration_range):
    """Generates random Job Shop data matching your matrix format."""
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
    for idx in range(NUM_INSTANCES):
        print(f"Generating instance {idx+1}/{NUM_INSTANCES}...")
        
        # A automatiser les combinaisons des nombres de jobs et machines !!!
        instance = generate_random_instance(NUM_JOBS[0], NUM_MACHINES[0], DURATION_RANGE[0])

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

        with open(DATASET_FILE, "a") as out_file:
            for i, sol in enumerate(solution_list):
                is_last = (i == len(solution_list) - 1)
                
                record = {
                    "instance": {
                        "source": "synthetic_generator",
                        "id": f"synth_{idx:04d}",
                        "num_jobs": instance["n_jobs"],
                        "num_machines": instance["n_machines"],
                        "durations": instance["job_task_duration"],
                        "machines": instance["job_task_machine"]
                    },
                    "solution": {
                        "starts": sol["x"],
                        "makespan": sol["C"],
                        "is_optimal": True if (is_last and final_status == "OPTIMAL_SOLUTION") else False
                    },
                    "solver_stats": {
                        "nodes": solver_stats.get("nodes", 0),
                        "failures": solver_stats.get("failures", 0),
                        "solve_time": solver_stats.get("solveTime", 0.0)
                    }
                }
                out_file.write(json.dumps(record) + "\n")

    if os.path.exists(temp_json):
        os.remove(temp_json)
        
    print("Dataset generation complete!")

if __name__ == "__main__":
    run_pipeline()