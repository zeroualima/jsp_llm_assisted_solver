import random
import json
import argparse
import os

# Expecting a dataset of 19500 instances
def split(input_path, train_path, val_path) :
    all_ids = set()
    with open(input_path, 'r') as f :
        for line in f :
            record = json.loads(line)
            all_ids.add(record["instance"]["id"])

    ids = list(all_ids)
    print("Detected number of IDs : ", len(ids))
    rng = random.Random(42)
    rng.shuffle(ids)

    train_ids = set(ids[:17550])
    val_ids = set(ids[17550:])

    train_lines = 0
    val_lines = 0

    with open(input_path, 'r') as f, \
        open(train_path, 'w') as ftrain, \
        open(val_path, 'w') as fval : 
        for line in f :
            record = json.loads(line)
            if record["instance"]["id"] in train_ids :
                ftrain.write(line)
                train_lines += 1
            else :
                fval.write(line)
                val_lines += 1

    print("Wrote ", train_lines, " records in train.jsonl")
    print("Wrote ", val_lines, " records in val.jsonl")

def parse_args() :
    parser = argparse.ArgumentParser(description="Filtered dataset 90/10 splitter")
    parser.add_argument("--input", type=str, required=True, help="Path to the filtered jsonl dataset")
    parser.add_argument("--train", type=str, required=True, help="Path to the train jsonl file")
    parser.add_argument("--val", type=str, required=True, help="Path to the val jsonl file")
    return parser.parse_args()


def main() :
    args = parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.train)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.val)), exist_ok=True)

    split(args.input, args.train, args.val)

if __name__ == "__main__" :
    main()
