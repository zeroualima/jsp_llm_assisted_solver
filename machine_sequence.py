def fill_seq(num_jobs, num_machines, machines):
    sequences = [[] for _ in range(num_machines)]
    for j in range(num_jobs):
        for i in range(num_machines):
            m = machines[j][i]
            sequences[m].append((j, i))
    return sequences

def sort_seq(sequences, starts):
    for m in range(len(sequences)):
        sequences[m].sort(key=lambda task: starts[task[0]][task[1]])
    return sequences


import json
line = '{"instance": {"source": "synthetic_generator", "id": "synth_t000_00040", "num_jobs": 3, "num_machines": 3, "durations": [[3, 2, 4], [4, 9, 7], [3, 3, 3]], "machines": [[1, 2, 0], [1, 2, 0], [1, 0, 2]]}, "solution": {"starts": [[0, 5, 9], [3, 7, 16], [10, 13, 20]], "makespan": 23, "optimal_makespan": 23, "gap_percent": 0.0, "is_optimal": true}, "solver_stats": {"nodes": 227, "failures": 5, "solve_time": 0.002}}'
record = json.loads(line)

num_jobs = record["instance"]["num_jobs"]
num_machines = record["instance"]["num_machines"]
machines = record["instance"]["machines"]
starts = record["solution"]["starts"]

sequences = fill_seq(num_jobs, num_machines, machines)
sequences = sort_seq(sequences, starts)

for m_seq in sequences :
  print(m_seq)