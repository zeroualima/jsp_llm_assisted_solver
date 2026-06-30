# """
# JSP Inference Script — load the fine-tuned model and generate warm-start
# predictions for new instances.

# Usage (interactive):
#     python3 inference.py

# This loads the base model + LoRA adapter once, then enters a loop where
# you can test multiple instances without reloading.
# """

# import json
# import torch
# from transformers import AutoTokenizer, AutoModelForCausalLM
# from peft import PeftModel

# MODEL_ID = "meta-llama/Meta-Llama-3.1-8B-Instruct"
# ADAPTER_PATH = "/home/mazerouali/jsp_records/checkpoints/final"
# HF_TOKEN = None  # will read from environment HF_TOKEN automatically

# import os
# HF_TOKEN = os.environ.get("HF_TOKEN")


# def load_model():
#     print("Loading tokenizer...")
#     tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, token=HF_TOKEN)
#     tokenizer.pad_token = tokenizer.eos_token

#     print("Loading base model (this takes a minute)...")
#     base_model = AutoModelForCausalLM.from_pretrained(
#         MODEL_ID,
#         token=HF_TOKEN,
#         dtype=torch.bfloat16,
#         device_map="auto",
#     )

#     print("Loading LoRA adapter...")
#     model = PeftModel.from_pretrained(base_model, ADAPTER_PATH)
#     model.eval()

#     print("Model ready.\n")
#     return model, tokenizer


# def build_prompt(instance):
#     """instance: dict with num_jobs, num_machines, durations, machines"""
#     prompt_obj = {
#         "num_jobs": instance["num_jobs"],
#         "num_machines": instance["num_machines"],
#         "durations": instance["durations"],
#         "machines": instance["machines"]
#     }
#     return f"<prompt>{json.dumps(prompt_obj)}</prompt><completion>"


# def generate_starts(model, tokenizer, instance, max_new_tokens=1024):
#     prompt_text = build_prompt(instance)
#     inputs = tokenizer(prompt_text, return_tensors="pt").to(model.device)

#     with torch.no_grad():
#         output_ids = model.generate(
#             **inputs,
#             max_new_tokens=max_new_tokens,
#             do_sample=False,          # greedy decoding for reproducibility
#             temperature=None,
#             top_p=None,
#             pad_token_id=tokenizer.eos_token_id,
#         )

#     full_text = tokenizer.decode(output_ids[0], skip_special_tokens=True)

#     # Extract just the completion part
#     if "<completion>" in full_text:
#         completion_text = full_text.split("<completion>")[1]
#         completion_text = completion_text.split("</completion>")[0]
#     else:
#         completion_text = full_text  # fallback, may need manual inspection

#     return completion_text, full_text

# def model_val(model, tokenizer, in_file, out_file) :
#     with open(in_file, 'r') as fin, open(out_file, 'w') as fout:
#         for line in fin :
#             record = json.loads(line)

#             instance = record["instance"]

#             completion_text, full_text = generate_starts(model, tokenizer, instance)

#             try:
#                 parsed = json.loads(completion_text)
#             except json.JSONDecodeError:
#                 if completion_text.strip().startswith('"'):
#                     fixed = "{" + completion_text
#                     parsed = json.loads(fixed)

#             out_file.write(json.dumps(parsed) + "\n")

# def main():
#     model, tokenizer = load_model()

#     # Example instance — replace with a real one from val_ft.jsonl for testing
#     example_instance = {
#         "num_jobs": 3,
#         "num_machines": 3,
#         "durations": [[10, 9, 1], [6, 10, 3], [1, 7, 9]],
#         "machines": [[2, 1, 0], [1, 2, 0], [2, 0, 1]]
#     }

#     print("Generating for example instance...")
#     completion_text, full_text = generate_starts(model, tokenizer, example_instance)

#     print("\n--- Raw completion text ---")
#     print(completion_text)

#     print("\n--- Attempting to parse as JSON ---")
#     try:
#         parsed = json.loads(completion_text)
#         print("Parsed successfully:")
#         print(parsed)
#     except json.JSONDecodeError as e:
#         print(f"Failed to parse: {e}")
#         print("Full raw output for debugging:")
#         print(full_text)


# if __name__ == "__main__":
#     main()
