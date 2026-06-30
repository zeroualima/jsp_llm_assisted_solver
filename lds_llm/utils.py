import json

def parse_model_starts(model_continuation):
    """Recover the JSON object, tolerating the missing leading '{\"'."""
    text = model_continuation
    if "</completion>" in text:
        text = text.split("</completion>")[0]
    text = text.strip()
    if not text.startswith("{"):
        text = "{\"" + text
    return json.loads(text)["starts"]

def precedences(num_jobs, num_machines, machines, starts) :
    x = [[[False for _ in range(num_machines)] for _ in range(num_jobs)] for _ in range(num_jobs)]
    # we just won't care about when a >= b, that's why it's False
    for m in range(num_machines) :
        for a in range(num_jobs - 1) :
            for b in range(a + 1, num_jobs) :
                t_a = sum(t for t in range(num_machines) if machines[a][t] == m)
                t_b = sum(t for t in range(num_machines) if machines[b][t] == m)
                if starts[a][t_a] < starts[b][t_b] :
                    x[a][b][m] = True
    return x