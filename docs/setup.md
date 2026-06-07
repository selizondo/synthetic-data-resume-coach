# Setup and Usage

## Key Concepts

**One resume per fit level with generation-time gate:** Each job generates exactly one resume per fit level (Excellent → Mismatch). Without explicit instructions, LLM defaults to plausible resumes at every level (Mismatch Jaccard 0.582). Overlap retry loop computes Jaccard post-generation, retries if outside target range (3x max). After gate: Excellent=0.979, Mismatch=0.000.

**Rule-based labeling:** Jaccard skill overlap, experience mismatch, seniority mismatch, missing core skill, hallucinated skill, language clarity. All deterministic, computed offline, zero API cost. LLM judge is opt-in and additive: catches subtle quality the rules miss.

**Pydantic errors as feedback:** Invalid pairs re-prompted with exact error messages (field path, error type, invalid value). Gives LLM precise context to fix without guessing. 100% correction on first attempt in proof-of-concept. In normal runs: `instructor` prevents schema-invalid generation.

**Fit-level distribution as the signal:** 8B model passed at 61.1%, stronger model at 31.6%. The lower number is correct: 8B ignored fit-level instructions and generated plausible resumes for every level. Stronger model with overlap retry produced real mismatches (avg Jaccard 0.000). Measurement: does distribution match what you asked for?

**Jaccard as fit-level measurement:** Measures overlap of skills between resume and job. Excellent resumes show high overlap (1.00), Mismatch shows none (0.00). The progression (1.00, 0.67, 0.43, 0.25, 0.00) validates that the generation-time gate is working.

---

## Prerequisites

- Python 3.12+
- `uv`: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Access to `selizondo/llm-utils` (private dep, required for `make bootstrap`)
- OpenAI-compatible API key (OpenAI, Groq, or local Ollama)

## Install

```bash
cp .env.example .env
# Edit .env: set LLM_API_KEY and LLM_MODEL at minimum
# Default: OpenAI gpt-4o-mini; see .env.example for Groq/Ollama alternatives

make bootstrap   # uv sync --all-extras
make test        # 57 tests, ~10 seconds, no API calls
```

## Run the Pipeline

```bash
make generate    # 10 jobs x 5 fit levels = 50 pairs
make serve       # FastAPI on 127.0.0.1:8000, interactive docs at /docs
```

## CLI Flags

```bash
# Resume an interrupted run (skips already-completed items)
python -m src.main --phase 3-4 --resume <run_label>

# Skip correction loop (faster, useful for exploration)
python -m src.main --num-jobs 10 --no-correction

# Skip chart generation
python -m src.main --num-jobs 10 --no-heatmaps

# Add LLM quality assessment (slower, costs tokens)
python -m src.main --num-jobs 10 --enable-llm-judge

# Run Phase 5 label quality report on a completed run
python -m src.main --eval-quality --resume <run_label>
```

## FastAPI Endpoints

`make serve` starts the API on `127.0.0.1:8000`. Interactive docs at `/docs`.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `POST` | `/review-resume` | Label a resume-job pair; returns `fit_score`, `overall_fit`, `strategy_used`, `latency_ms` |
| `GET` | `/analysis/failure-rates` | Aggregate failure rates from a completed run (requires `run_label` query param) |
| `GET` | `/analysis/label-quality` | Per-metric quality report (requires `run_label` from a `--eval-quality` run) |

## Output Structure

```
data/
├── generated/
│   ├── jobs_<run>.jsonl              # One JobDescription per line
│   ├── pairs_<run>.jsonl             # One ResumeJobPair per line (5 fit levels per job)
│   └── resumes_<run>.jsonl           # Extracted resumes (one per pair)
├── validated/
│   ├── validated_data_<run>.json     # Validation summary + valid trace IDs
│   ├── schema_failure_modes_<run>.json
│   └── corrections_<run>.json        # Only written when correction loop processes records
├── labeled/
│   ├── failure_labels_<run>.jsonl    # 6 rule-based metrics per pair
│   ├── failed_pairs_<run>.jsonl      # Pairs that failed labeling
│   └── label_quality_<run>.json      # Per-metric quality report (--eval-quality flag)
├── pipeline_summary_<run>.json       # Timing + counts
└── iteration_log.jsonl               # Before/after delta across all runs
```

`run_label` is a timestamp (`YYYYMMDD_HHMMSS`) assigned at pipeline start.

## Code Layout

```
synthetic-data-resume-coach/
├── src/
│   ├── main.py                       # CLI entry point
│   ├── generation/                   # Phase 1: LLM generation with fit-level prompts
│   ├── validation/                   # Phase 2: Pydantic schema gates
│   ├── analysis/
│   │   └── failure_labeler.py        # Phase 3: 6 rule-based metrics
│   ├── correction/                   # Phase 4: LLM re-prompt with Pydantic errors
│   └── api/                          # FastAPI service
├── tests/                            # 57 tests, no LLM calls
└── docs/
    ├── engineering.md                # Design decisions
    ├── evidence.md                   # Iteration log, spot-check, correction proof
    └── failures.md                   # Known failure modes
```
