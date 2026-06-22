from minizinc import Instance, Model, Solver

chuffed = Solver.lookup("chuffed")

model = Model("./Generate_Dataset/model.mzn")

def func(instance, initial_llm_sequence) :
    precedences = [[[0 for _ in num_machines] for _in num_jobs] for _ in num_jobs]
    for i in range(num_jobs) :
        for j in range(num_jobs) :
            for m in range(num_machines) :
                if starts[i][m] < starts[j][m] :
                    precedences[i][j][m] = 1
    return precedences


def run_lds_loop(instance, initial_llm_sequence) :