import os
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer, SFTConfig
from datasets import load_dataset

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL_ID       = "meta-llama/Meta-Llama-3.1-8B-Instruct"
HF_TOKEN       = os.environ["HF_TOKEN"]
TRAIN_FILE     = "/home/mazerouali/jsp_records/train_ft.jsonl"
VAL_FILE       = "/home/mazerouali/jsp_records/val_ft.jsonl"
OUTPUT_DIR     = "/home/mazerouali/jsp_records/checkpoints"
MAX_SEQ_LEN    = 2048
BATCH_SIZE     = 4
GRAD_ACC_STEPS = 8
NUM_EPOCHS     = 3
LEARNING_RATE  = 2e-4

# ---------------------------------------------------------------------------
# 4-bit quantization config (QLoRA)
# ---------------------------------------------------------------------------

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

# ---------------------------------------------------------------------------
# Load model and tokenizer
# ---------------------------------------------------------------------------

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, token=HF_TOKEN)
tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "right"

model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    token=HF_TOKEN,
    quantization_config=bnb_config,
    device_map="auto",
    torch_dtype=torch.bfloat16,
)
model.config.use_cache = False

# ---------------------------------------------------------------------------
# LoRA config (RSLoRA, rank 64)
# ---------------------------------------------------------------------------

lora_config = LoraConfig(
    r=64,
    lora_alpha=64,
    use_rslora=True,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj"
    ],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)

model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

dataset = load_dataset(
    "json",
    data_files={"train": TRAIN_FILE, "validation": VAL_FILE}
)

# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

sft_config = SFTConfig(
    output_dir=OUTPUT_DIR,
    num_train_epochs=NUM_EPOCHS,
    per_device_train_batch_size=BATCH_SIZE,
    per_device_eval_batch_size=BATCH_SIZE,
    gradient_accumulation_steps=GRAD_ACC_STEPS,
    learning_rate=LEARNING_RATE,
    lr_scheduler_type="cosine",
    warmup_ratio=0.05,
    bf16=True,
    max_length=MAX_SEQ_LEN,
    dataset_text_field="text",
    logging_steps=50,
    eval_strategy="epoch",
    save_strategy="epoch",
    save_total_limit=2,
    load_best_model_at_end=True,
    report_to="none",
)

trainer = SFTTrainer(
    model=model,
    args=sft_config,
    train_dataset=dataset["train"],
    eval_dataset=dataset["validation"],
    processing_class=tokenizer,
)

trainer.train()
trainer.save_model(OUTPUT_DIR + "/final")
