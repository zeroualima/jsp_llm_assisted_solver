import itertools

combinations = list(itertools.product([[1, 10], [2, 20]], [100, 200]))
print(combinations)
print(len(combinations))