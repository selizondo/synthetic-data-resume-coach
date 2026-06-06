# Setup and Usage

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
