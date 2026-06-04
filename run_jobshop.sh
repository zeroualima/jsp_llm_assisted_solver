#!/bin/bash

# if [ "$#" -ne 2 ]; then
#     echo "Usage: ./run_jobshop.sh <model.mzn> <data.dzn>"
#     exit 1
# fi

# MODEL=$1
# DATA=$2
MODEL="jsp/model.mzn"
DATA="jsp/data.dzn"
STARTS="jsp/starts.txt"
CSV="jsp/results.csv"

echo "--- Step 1: Solving with MiniZinc ---"
minizinc --solver chuffed --statistics -t 300000 "$MODEL" "$DATA" > "$STARTS"

if [ $? -eq 0 ]; then
    echo "Success: Solution found and saved to $STARTS"
else
    echo "Error: MiniZinc failed to solve."
    exit 1
fi

echo "--- Step 2: Processing data with C++ ---"
g++ -o main main.cpp parser.cpp
./main "$STARTS" "$DATA"

if [ $? -eq 0 ]; then
    echo "Success: $CSV generated."
else
    echo "Error: C++ processing failed."
    exit 1
fi

echo "--- You can check dataset.jsonl ---"
# echo "--- Step 3: Visualizing with Python ---"
# python3 visual.py