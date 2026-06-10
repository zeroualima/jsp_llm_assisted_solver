import json
import argparse
import os

def transform(input_path, output_path):
    with open(input_path, 'r') as fin, open(output_path, 'w') as fout:
        for line in fin:
            record = json.loads(line)
            
            prompt_obj = {
                "num_jobs":   record["instance"]["num_jobs"],
                "num_machines": record["instance"]["num_machines"],
                "durations":  record["instance"]["durations"],
                "machines":   record["instance"]["machines"]
            }
            
            completion_obj = {
                "starts":   record["solution"]["starts"],
                "makespan": record["solution"]["makespan"]
            }
            
            text = (
                f"<prompt>{json.dumps(prompt_obj)}</prompt>"
                f"<completion>{json.dumps(completion_obj)}</completion>"
            )
            
            fout.write(json.dumps({"text": text}) + "\n")

def parse_args() :
    parser = argparse.ArgumentParser(description="JSP data generator (for fine-tuning)")
    parser.add_argument("--input", type=str, required=True, help="Path to the jsonl dataset")
    parser.add_argument("--output", type=str, required=True, help="Path to the output file")
    return parser.parse_args()


def main() :
    args = parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    transform(args.input, args.output)

if __name__ == "__main__" :
    main()
