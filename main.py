from minizinc import Instance, Model, Solver
import json
from llm import generate_continuation
from utils import parse_model_starts, precedences

def solve(instance) :
    num_jobs = instance["num_jobs"]
    num_machines = instance["num_machines"]
    durations = instance["durations"]
    machines = instance["machines"]

    prompt = f"<prompt>{json.dumps(instance)}</prompt><completion>"
    llm_continuation = generate_continuation(prompt)

    try:
        llm_starts = parse_model_starts(llm_continuation)
    except (json.JSONDecodeError, KeyError, IndexError):
        return None

    llm_precedences = precedences(num_jobs, num_machines, machines, llm_starts)

    return lds(num_jobs, num_machines, durations, machines, llm_precedences)

def lds(J, M, durations, machines, x) :
    chuffed = Solver.lookup("chuffed")
    model = Model("jssp_lds.mzn")
    jssp = Instance(chuffed, model)

    jssp["J"] = J
    jssp["M"] = M
    jssp["durations"] = durations
    jssp["machines"] = machines
    jssp["x"] = x

    k = 0
    k_max = J * (J-1)//2 * M 

    result = None
    while k <= k_max:
        jssp["k"] = k
        response = jssp.solve()
        if response.status.has_solution():
            result = response
            break
        k += 1

    return result


instance = {
    "num_jobs": 3, 
    "num_machines": 3,
    "durations": [[10, 9, 1], [6, 10, 3], [1, 7, 9]],
    "machines": [[2, 1, 0], [1, 2, 0], [2, 0, 1]]
}

result = solve(instance)

print(result)

