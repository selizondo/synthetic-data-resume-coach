# Synthetic Data Resume Coach — Developer Guide

End-to-end pipeline that generates, validates, labels, and corrects synthetic resume–job-description
pairs for training resume-matching models.

---

## What this project does

1. **Generate** — an LLM produces job descriptions + 5 resumes per job at controlled fit levels
   (Excellent → Mismatch). Each item gets a stable `trace_id` for lineage.
2. **Validate** — Pydantic schemas gate every record. Invalid records are saved separately for correction.
3. **Label** — six rule-based failure metrics (skills overlap, experience gap, seniority mismatch,
   missing core skill, hallucination, awkward language) are computed per pair.
4. **Correct** — invalid records are fed back to the LLM with their error messages; re-validated up
   to 3 times.
5. **API** — a FastAPI server exposes single-pair review and aggregate failure-rate endpoints.

---

## Quick start

### 1. Prerequisites

- Python 3.12
- [`uv`](https://docs.astral.sh/uv/) (recommended) or `pip`
- A Groq API key (free tier works; see rate-limit notes below)

### 2. Clone and install

```bash
# From the repo root
cd synthetic_data_resume_coach

# Install project + dev deps (uv recommended)
uv pip install -e ".[dev]"

# Also install the shared LLM utility package (local editable)
uv pip install -e ../llm_utils/
```

> **Important:** always run commands from the `synthetic_data_resume_coach/` directory.
> The `.env` file is loaded relative to CWD at import time. Running from a parent directory
> will silently use the wrong model.

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
# Required — generation model
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=gsk_...                    # your Groq key
LLM_MODEL=llama-3.1-8b-instant         # 15k TPM free tier

# Rate limiting — prevents Groq 429s
LLM_RATE_LIMIT_DELAY=4.0               # seconds between generation calls

# Optional — separate judge model (defaults to generation values if unset)
# LLM_JUDGE_BASE_URL=https://api.openai.com/v1
# LLM_JUDGE_API_KEY=sk-...
# LLM_JUDGE_MODEL=gpt-4o-mini
# LLM_JUDGE_RATE_LIMIT_DELAY=0.0

# Optional — observability
LOGFIRE_TOKEN=...                       # leave unset to disable
LOGFIRE_SEND_TO_LOGFIRE=false           # set true to send traces to Logfire cloud
```

#### Provider / rate-limit reference

| Provider | Model | TPM cap | Recommended `LLM_RATE_LIMIT_DELAY` |
|---|---|---|---|
| Groq (free) | `llama-3.1-8b-instant` | 15 000 | `4.0` |
| Groq (free) | `llama-3.3-70b-versatile` | 6 000 | `15.0` |
| OpenAI | `gpt-4o-mini` | ~200 000 | `0.0` |
| Ollama (local) | any | unlimited | `0.0` |

### 4. Verify setup

```bash
python -m pytest tests/ -q
# Expected: 41 passed
```

---

## Running the pipeline

All commands use `python -m src.main` from the project root.

### Full run (phases 1–4)

```bash
python -m src.main --num-jobs 10 --resumes-per-job 5
```

This generates a `run_label` (timestamp) and writes all output under `data/`.

### Partial run / resume after interruption

Each item is written to JSONL immediately — if the pipeline is killed mid-run, resume
with the same `run_label` printed at startup:

```bash
python -m src.main --num-jobs 50 --resume 20260502_075406
```

Only missing items are generated; already-completed ones are skipped.

### Run specific phases

```bash
# Phase 1 only (generate)
python -m src.main --phase 1 --num-jobs 10

# Phases 2–4 against an existing run
python -m src.main --phase 2-4 --resume 20260502_075406

# Phase 3 only (re-label existing pairs)
python -m src.main --phase 3 --resume 20260502_075406
```

### All CLI flags

```
--num-jobs, -n       Number of job descriptions to generate (default: 10)
--resumes-per-job    Resumes per job, one per fit level (default: 5)
--model, -m          LLM model override (default: LLM_MODEL env var)
--judge-model        Judge model override (default: --model)
--phase              Phase range: "1-4", "1", "2-4", "3" etc. (default: "1-4")
--resume             Resume a prior run by its run_label timestamp
--output-dir, -o     Output root directory (default: data)
--no-correction      Skip Phase 4 correction loop
--no-heatmaps        Skip matplotlib chart generation
--enable-llm-judge   Run LLM judge in Phase 3 (slower, costs tokens)
--enable-braintrust  Log to Braintrust (requires BRAINTRUST_API_KEY)
```

---

## Running tests

```bash
# All tests
python -m pytest tests/ -q

# Specific test class
python -m pytest tests/test_pipeline.py::TestFailureLabeler -v

# With full output on failure
python -m pytest tests/ --tb=short
```

The test suite is fully offline — no LLM calls, no network. All 41 tests should pass
in under 10 seconds.

---

## Starting the API server

```bash
uvicorn src.api.main:app --reload --port 8000
```

Interactive docs at [http://localhost:8000/docs](http://localhost:8000/docs).

### Endpoints

| Method | Path | What it does |
|---|---|---|
| `GET` | `/` | API info + version |
| `GET` | `/health` | Health check |
| `POST` | `/review-resume` | Analyze a single resume against a job description |
| `GET` | `/analysis/failure-rates` | Aggregate failure stats from the latest labeled JSONL file |

#### Example: review a resume

```bash
curl -X POST http://localhost:8000/review-resume \
  -H "Content-Type: application/json" \
  -d '{
    "resume": {
      "contact": {"name": "Jane Smith", "email": "jane@example.com",
                  "phone": "555-123-4567", "location": "Austin, TX"},
      "education": [{"degree": "BS Computer Science",
                     "institution": "UT Austin", "graduation_date": "2020-05-15"}],
      "skills": [{"name": "Python", "proficiency_level": "Expert"},
                 {"name": "SQL", "proficiency_level": "Advanced"}]
    },
    "job_description": {
      "title": "Data Engineer",
      "company": {"name": "Acme Corp", "industry": "Technology",
                  "size": "Medium", "location": "Remote"},
      "description": "We are hiring a data engineer to build and maintain data pipelines for our analytics platform.",
      "requirements": {
        "required_skills": ["Python", "SQL", "Airflow"],
        "education_requirements": "BS in CS or related",
        "experience_years": 3,
        "experience_level": "Mid"
      },
      "responsibilities": ["Build pipelines", "Maintain data quality"]
    },
    "use_llm_judge": false
  }'
```

Response includes `overall_fit`, `fit_score`, `skill_analysis`, `failure_flags`, and `recommendations`.

---

## Project layout

```
synthetic_data_resume_coach/
├── src/
│   ├── main.py                  # CLI entry point + phase orchestrator
│   ├── config.py                # PipelineConfig dataclass
│   ├── schema.py                # All Pydantic models (Resume, JobDescription, pairs)
│   ├── generators.py            # ResumeGenerator + JobDescriptionGenerator
│   ├── prompts.py               # YAML prompt loader
│   ├── phase1_generation.py     # Incremental generation + checkpoint recovery
│   ├── phase2_validation.py     # Schema validation + heatmaps
│   ├── phase3_labeling.py       # Failure mode labeling
│   ├── phase4_correction.py     # LLM correction loop
│   ├── analysis/
│   │   ├── failure_labeler.py   # 6-metric rule-based labeler (Jaccard, seniority, etc.)
│   │   ├── failure_modes.py     # FailureModeAnalyzer — schema error categorization
│   │   ├── heatmap.py           # Matplotlib chart generators
│   │   └── llm_judge.py        # Optional LLM-based quality judge
│   ├── api/
│   │   ├── main.py              # FastAPI app + lifespan
│   │   └── routes.py            # /review-resume and /analysis/failure-rates
│   ├── correction/
│   │   └── llm_correction.py   # Iterative LLM correction with re-validation
│   ├── validators/
│   │   └── schema_validator.py  # SchemaValidator wrapping Pydantic
│   ├── failure_modes/           # YAML definitions for each failure mode
│   ├── prompts/                 # YAML resume prompt templates (formal, casual, etc.)
│   └── utils/
│       ├── storage.py           # save_jsonl, load_jsonl, JSONLWriter
│       └── trace.py             # generate_trace_id
├── data/
│   ├── generated/               # jobs_<run>.jsonl, pairs_<run>.jsonl, resumes_<run>.jsonl
│   ├── labeled/                 # failure_labels_<run>.jsonl, failed_pairs_<run>.jsonl
│   │   └── visualizations/      # PNG heatmaps per run
│   └── validated/               # corrections_<run>.json, field-level heatmaps
├── tests/
│   └── test_pipeline.py         # 41 unit + integration tests (fully offline)
├── pyproject.toml
├── .env.example
└── synthetic_data_resume_coach.md   # Full project spec (read-only)
```

---

## Output files

| File | What's in it |
|---|---|
| `data/generated/jobs_<run>.jsonl` | One `JobDescription` JSON per line |
| `data/generated/resumes_<run>.jsonl` | One `Resume` JSON per line |
| `data/generated/pairs_<run>.jsonl` | One `ResumeJobPair` JSON per line — primary dataset |
| `data/labeled/failure_labels_<run>.jsonl` | One `FailureLabels` record per pair |
| `data/labeled/failed_pairs_<run>.jsonl` | Subset of pairs that failed labeling |
| `data/validated/corrections_<run>.json` | Correction loop results + stats (JSON, not JSONL) |
| `data/pipeline_summary_<run>.json` | Phase timings, counts, file paths for the full run |
| `data/iteration_log.jsonl` | Appended after each run — delta tracking across runs |

---

## Key concepts

**Fit levels** control how well the generated resume matches the job.
The prompt instruction per level:

| Level | Skill coverage |
|---|---|
| Excellent | All required skills, Expert proficiency |
| Good | 80% of required skills, Advanced |
| Partial | ~50% of required skills, mixed |
| Poor | 20–30% of required skills, mostly Beginner |
| Mismatch | Skills from a completely different field |

**Checkpoint recovery** — Phase 1 writes each generated item immediately to JSONL.
If the process is killed (e.g., rate-limit circuit breaker trips), the `--resume <run_label>`
flag picks up exactly where it left off, per job and per fit level.

**Circuit breaker** — after 2 consecutive 429 errors, Phase 1 stops and prints the resume
command. Wait ~60 seconds for Groq's rolling window to reset before resuming.

---

## Common issues

**`NameError: name 'gen' is not defined`**
You passed `--phase 2-4` without `--resume`. Provide the `run_label` from a completed
Phase 1 run: `--phase 2-4 --resume <run_label>`.

**`LLM_API_KEY is not set`**
Your `.env` is not being found. Make sure you're running from the `synthetic_data_resume_coach/`
directory, not a parent directory.

**Silent wrong model** (e.g., running a 70b model when you expected 8b)
`get_settings()` caches on first import. If you `cd` into a different directory after
import, the wrong `.env` may already be loaded. Always start a fresh shell from the
project directory.

**Tests fail with `ModuleNotFoundError: No module named 'llm_utils'`**
The local `llm_utils` package must be installed in editable mode:
`uv pip install -e ../llm_utils/`

**Heatmaps not generating**
Matplotlib requires a display. On headless servers, set `MPLBACKEND=Agg` in your environment
or pass `--no-heatmaps`.
