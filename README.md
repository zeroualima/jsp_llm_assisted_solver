This repository archives the experimental code, scripts, and data pipelines developed during a three-month Assistant Engineer internship at LAAS-CNRS. The project investigates whether a Large Language Model (LLM) fine-tuned on solved instances can accelerate an exact Constraint Programming (CP) solver for the Job-Shop Scheduling Problem (JSSP). Instead of relying on the LLM for an end-to-end solution, the model generates an informed "warm start" that is refined by the CP solver using a Limited Discrepancy Search (LDS).

### A Note on the Codebase

Because this was an exploratory operations research project, much of the codebase consists of highly experimental, single-use scripts utilized for massive data generation, model fine-tuning, and metric extraction. The repository is preserved "as is" to document the complete pipeline and the empirical results that formed the final evaluation.

## System Architecture & Pipeline

* **Dataset Generation:** A parallelized pipeline utilizing Python and C++ was deployed via SLURM batch scripts on the LAAS computing cluster to generate over 25 million solved JSSP instances using MiniZinc and the Chuffed solver. This raw data was filtered to retain only high-quality solutions (within a 3% gap of optimality), resulting in a training set of 145,330 records.


* **LLM Fine-Tuning:** A LLaMA 3.1 8B Instruct model was fine-tuned using Low-Rank Adaptation (LoRA), RSLoRA, and 4-bit quantization (QLoRA) via Hugging Face's PEFT and TRL libraries. Training was conducted on RTX A6000 GPUs, requiring 6-9 days of continuous GPU time per variant.


* **Solver Integration (LDS):** The LLM's proposed schedule is injected into the CP model as a soft constraint. A discrepancy budget $k$ bounds the number of precedence decisions the solver is allowed to flip to repair the LLM's mistakes. If the proposal is strictly feasible, $k=0$; otherwise, $k$ is incrementally relaxed until feasibility is established.



## Experimental Output Representations

The core of the research evaluated four distinct LLM output representations to determine which format the model could most reliably learn and generate:

* **V1 (Numerical Start Times):** The LLM directly predicts numerical start times $S_{j,m}$. This approach suffered heavily from silent truncation during training due to token limits being exceeded on larger instances.


* **V2 (Per-Machine JSON):** The LLM outputs the implied job sequence for each machine in JSON. While structurally fragile (only 26.21% of outputs were valid JSON), the structurally valid proposals resolved very efficiently within the LDS framework.


* **V3 (Natural Language):** The same sequencing information as V2, but formatted in conversational English to test if the LLM's pre-training inductive bias would improve generation. This was a total failure: 99.69% of responses were unparseable, proving that free-form prose removes necessary syntactic scaffolding.


* **V4 (Operation-Based Array / Bierwirth):** Represents the schedule as a global sequence of $J \times M$ operations. This was the most successful approach, guaranteeing feasibility by construction.



## Key Findings

* The V4 (Bierwirth) representation proved highly reliable for instances up to $12\times12$, successfully decoding to a valid schedule for 76.97% of the 1,950 held-out validation instances without any solver intervention ($k=0$).


* LLM performance collapsed on the largest instances (e.g., $15\times12$ and $20\times15$) due to a generative repetition-loop failure mode where the model lost track of per-job occurrence counts.


* The study confirms that an LLM-generated warm start effectively reduces a CP solver's search space, provided the output format avoids cyclic dependencies and its failure modes remain tractable for the solver to absorb.



## Technical Stack

* **Optimization & CP:** MiniZinc, Chuffed
* **Machine Learning:** PyTorch, Hugging Face (PEFT, TRL, Transformers), LLaMA 3.1 8B
* **Languages & Infrastructure:** Python, C++, SLURM, Linux Cluster Computing
