# synthetic-data-resume-coach

![Tests](https://github.com/selizondo/synthetic-data-resume-coach/actions/workflows/ci.yml/badge.svg)

ML teams training resume-matching models need labeled data, but manually labeled pairs are expensive, slow, and inconsistent. Synthetic data solves the cost problem but creates a harder one: without independent validation, you can't tell whether the generated pairs actually span the distribution you need — or whether the LLM quietly hallucinated half the fields.

This project is a production-grade synthetic data pipeline that generates resume–job-description pairs at five calibrated fit levels, validates every pair against a strict Pydantic schema, labels each one with six independent failure metrics, and corrects failures by re-prompting the LLM with its own error messages. It also ships a FastAPI service that runs the same labeling logic on demand.

---

## Engineering Decisions

**LLMs default to generating "good enough" resumes.** Without explicit instructions, you get a pile of mid-range fits and almost no true mismatches or excellent candidates — which makes it impossible to train a model that can distinguish between them. Each job generates exactly one resume per fit level using structured prompts that specify exact skill coverage targets (e.g., "include only 20–30% of required skills" for Poor). This is the only reliable way to cover the full fit spectrum.

**Generated data can be structurally broken with no visible error.** A hallucinated `null` date or a missing required field poisons the training set silently. Every pair is gated through Pydantic schema validation before it enters the labeled dataset. Invalid pairs are quarantined to `failed_pairs_<run>.jsonl` for correction rather than silently dropped.

**Invalid records need a correction signal, not a gold standard.** There's no human-labeled "right answer" to correct toward. The correction loop re-prompts the LLM with its own Pydantic error messages (up to 3 retries), using the validator output as the feedback signal. Before/after deltas are logged per run.

**Crash recovery without re-generation.** Phase 1 writes each item to JSONL immediately. If the process is killed mid-run (rate-limit, OOM), `--resume <run_label>` picks up at the exact item where it stopped.

**Rule-based labeler, not LLM-based.** The six failure metrics are deterministic, instant, and free. The LLM judge (`--enable-llm-judge`) is additive — it catches subtle quality issues the rules miss, but rules gate correctness first.

**API responses include `strategy_used` and `latency_ms`.** Callers can alert on latency regression or distinguish `rule_based` from `rule_based+llm_judge` paths without parsing logs.

---

## How It's Structured

```
LLM (any OpenAI-compatible endpoint — OpenAI, Groq, Ollama)
        │
        ▼ Phase 1: Generate
jobs_<run>.jsonl    — one JobDescription per line, trace_id stamped
pairs_<run>.jsonl   — one ResumeJobPair per line, 5 fit levels per job
resumes_<run>.jsonl — extracted resumes (one per pair)
        │
        ▼ Phase 2: Validate
Pydantic schema gates all fields
→ valid pairs continue; invalid → failed_pairs_<run>.jsonl
        │
        ▼ Phase 3: Label
6 rule-based metrics per pair:
  skills_overlap_ratio (Jaccard), experience_mismatch, seniority_mismatch,
  missing_core_skill, hallucinated_skill, awkward_language_flag
→ failure_labels_<run>.jsonl
        │
        ▼ Phase 4: Correct
LLM re-prompted with Pydantic error messages for failed pairs (≤3 retries)
→ corrections_<run>.json (before/after delta per run label)
        │
        ▼ FastAPI /review-resume
Jaccard + 5 binary gates → { fit_score, overall_fit, strategy_used, latency_ms }
```

---

## Key Concepts

### Fit Levels

Each job generates exactly one resume per fit level. The target Jaccard overlap is controlled at generation time via per-level prompt instructions:

| Fit Level | Jaccard Target | What it means |
|---|---|---|
| Excellent | ≥ 0.80 | Strong skill match; resume is a genuine candidate |
| Good | 0.60–0.80 | Solid overlap with minor gaps |
| Partial | 0.40–0.60 | Notable gaps but viable with upskilling |
| Poor | 0.20–0.40 | Significant mismatch; missing core skills |
| Mismatch | < 0.20 | Wrong role entirely |

Without explicit instructions, an LLM defaults to generating plausible resumes — you get plenty of "good" fits but almost never a true mismatch or an excellent one. Per-level prompts fix this by telling the model exactly what overlap to aim for.

### Failure Metrics

Six rule-based metrics are computed for every resume–job pair by `src/analysis/failure_labeler.py`:

| Metric | Calculation | Flag condition |
|---|---|---|
| **skills_overlap_ratio** | Jaccard: `\|A ∩ B\| / \|A ∪ B\|` on normalized skill sets | Continuous 0–1 |
| **experience_mismatch** | Resume years < 50% of required, or gap > 2 years | Binary |
| **seniority_mismatch** | Seniority level distance > 1 | Binary |
| **missing_core_skill** | Absence of any top-3 required skill | Binary |
| **hallucinated_skill** | Entry-level with 10+ "Expert" ratings, or 20+ skills total | Binary |
| **awkward_language_flag** | Buzzword density > 5 per section; repeated jargon patterns | Binary |

Seniority levels are mapped to integers: Entry=0, Mid=1, Senior=2, Lead/Staff=3, Executive=4. A mismatch fires when `|resume_level − job_level| > 1`.

### Skill Normalization

Jaccard is only meaningful if "Python", "Python 3.10", and "python developer" resolve to the same token. The labeler normalizes all skill strings before comparison:

1. Lowercase
2. Strip version numbers (`3.10`, `v2`, `2.x`)
3. Strip common suffixes (`.js`, `developer`, `engineer`, `programming`)

Without normalization, Jaccard scores are artificially low and the fit level distribution collapses toward "poor" regardless of actual alignment.

### Resume Writing Templates

Each resume is generated using one of five prompt templates, recorded in the `writing_style` metadata field:

| Template | Characteristics |
|---|---|
| Formal | Corporate tone, structured, passive voice |
| Casual | Startup-friendly, first-person, conversational |
| Technical | Detail-heavy, emphasizes stack depth and tooling |
| Achievement | Metrics-driven, quantified impact statements |
| Career-changer | Transferable skills framing, reframes prior experience |

Failure detection must work across all five styles — a hallucination detector tuned only on formal resumes will miss patterns in casual ones.

---

## Results

| Metric | Value |
|---|---|
| Overall labeler pass rate | 31.6% across 250 pairs (50 jobs × 5 fit levels) |
| Dominant failure mode | Missing core skill (43.2%) |
| Schema validation rate | 100% — all generated pairs pass Pydantic |
| Average skill overlap | 0.50 across all fit levels |
| Test suite | 57 tests, fully offline (no LLM calls) |

A 31.6% pass rate is expected — Poor and Mismatch pairs fail the labeler by design (they intentionally lack required skills). The signal is whether the rate holds stable across runs and whether failure modes track the fit level distribution.

**Failure rates by mode (50-job run):**

| Failure Mode | Rate |
|---|---|
| Missing core skill | 43.2% |
| Seniority mismatch | 26.0% |
| Low skills overlap (<0.5 Jaccard) | 56.0% |
| Experience mismatch | 12.8% |
| Awkward language | 5.6% |
| Hallucinated skill | 0.8% |

---

## At Scale

At org scale, any AI team training on synthetic data faces the same governance question: how do you know your synthetic distribution matches the real one? This pipeline operationalizes a validation-first answer — every pair is independently scored by six rule-based metrics before it enters the training corpus, failed pairs are corrected and re-scored rather than discarded, and the correction loop's before/after delta is tracked across runs. The pattern — generate → validate schema → label failure modes → correct with error context — applies to any LLM-generated training corpus regardless of domain. A team building customer-intent training data, legal-clause classifiers, or code-review datasets runs the same four phases against a different schema and a different labeler.

---

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Access to `selizondo/llm-utils` (private dep — required for `make bootstrap` to succeed)
- An OpenAI-compatible LLM API key (OpenAI, Groq, or local Ollama)

### Setup

```bash
cp .env.example .env
# Edit .env — set LLM_API_KEY and LLM_MODEL at minimum
# Default is OpenAI gpt-4o-mini; see .env.example for Groq/Ollama alternatives

make bootstrap         # uv sync --all-extras — installs all deps including dev tools
make test              # 57 tests, ~10 seconds, no API calls
```

### Run the pipeline

```bash
make generate          # 10 jobs × 5 fit levels = 50 pairs; heatmaps disabled by default
make serve             # FastAPI on 127.0.0.1:8000 — interactive docs at /docs
```

### Output structure

```
data/
├── generated/
│   ├── jobs_<run_label>.jsonl       # one JobDescription per line
│   ├── pairs_<run_label>.jsonl      # one ResumeJobPair per line (5 fit levels per job)
│   └── resumes_<run_label>.jsonl
├── validated/
│   └── validation_report_<run_label>.json
├── labeled/
│   └── failure_labels_<run_label>.jsonl  # 6 rule-based metrics per pair
├── pipeline_summary_<run_label>.json     # timing + counts for the full run
└── iteration_log.jsonl                   # before/after delta across all runs
```

`run_label` is a timestamp (`YYYYMMDD_HHMMSS`) assigned at pipeline start.

### Key CLI flags

```bash
# Resume a run that was interrupted (skips already-completed items)
python -m src.main --phase 3-4 --resume 20260528_185335

# Skip correction loop (faster; useful for exploration)
python -m src.main --num-jobs 10 --no-correction

# Run on a headless server (heatmaps require a display)
python -m src.main --num-jobs 10 --no-heatmaps

# Add LLM-based quality assessment (slower, costs tokens)
python -m src.main --num-jobs 10 --enable-llm-judge

# Run Phase 5 label quality report against a completed run
python -m src.main --eval-quality --resume 20260528_185335
```

See [docs/tradeoffs.md](docs/tradeoffs.md) for design decisions and [docs/failures.md](docs/failures.md) for known failure modes.

**Blog post:** [docs/blog_post.md](docs/blog_post.md)

---

## Related Projects

| Repo | Relationship |
|---|---|
| [llm-utils](../llm-utils) | Shared LLM client with retry/backoff used in generation + correction |
| [synthetic-data-diy](../synthetic-data-diy) | Same pipeline pattern applied to home DIY repair Q&A |
