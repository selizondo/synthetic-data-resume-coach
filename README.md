# synthetic-data-resume-coach

![Tests](https://github.com/selizondo/synthetic-data-resume-coach/actions/workflows/ci.yml/badge.svg)

ML teams training resume-matching models need labeled data, but manually labeled pairs are expensive, slow, and inconsistent. Synthetic data solves the cost problem but creates a harder one: without independent validation, you can't tell whether the generated pairs actually span the distribution you need — or whether the LLM quietly hallucinated half the fields.

This project is a production-grade synthetic data pipeline that generates resume–job-description pairs at five calibrated fit levels, validates every pair against a strict Pydantic schema, labels each one with six independent failure metrics, and corrects failures by re-prompting the LLM with its own error messages. It also ships a FastAPI service that runs the same labeling logic on demand.

---

## The Core Engineering Problem

Three failure modes that LLM-generated training data introduces — each detected and handled:

**1. Distribution collapse** — Unconstrained LLM generation clusters near "good enough" and never produces the extremes (Excellent, Mismatch) that train a discriminative model. Fix: each job generates exactly one resume per fit level via structured prompts with per-level skill coverage targets (e.g., "include only 20–30% of required skills, mostly Beginner" for Poor).

**2. Silent schema violations** — An LLM that hallucinates `null` dates or omits required skills fields poisons the training set with no error. Fix: Pydantic schema gates every pair before it enters the labeled dataset. Failed pairs are quarantined to `failed_pairs_<run>.jsonl` for correction, not silently dropped.

**3. No supervision signal for correction** — When a pair fails, there's no gold standard to correct toward. Fix: the correction loop re-prompts the LLM with its own schema error messages (up to 3 retries), using the validator's output as the supervision signal. The before/after delta is logged per run for drift tracking.

---

## How It's Structured

```
LLM (Groq llama-3.x or any OpenAI-compatible endpoint)
        │
        ▼ Phase 1: Generate
jobs_<run>.jsonl    — one JobDescription per line, trace_id stamped
pairs_<run>.jsonl   — one ResumeJobPair per line, 5 fit levels per job
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

## Results

| Metric | Value |
|---|---|
| Overall pass rate | 61% across 5 fit levels |
| Dominant failure mode | Seniority mismatch (19.7%) |
| Correction loop success | ~40% of failed pairs corrected on retry |
| Validation rate | >90% of generated pairs pass schema |
| Test suite | 41 tests, fully offline (no LLM calls) |

A 61% pass rate is expected — "Mismatch" pairs fail the labeler by design. The signal is whether the rate holds stable across runs and whether failure modes track the fit level distribution.

---

## Staff-Level Design Decisions

**Checkpoint recovery** — Phase 1 writes each item to JSONL immediately. If the process is killed (rate-limit circuit breaker, OOM), `--resume <run_label>` picks up at the exact item where it stopped. No re-generation of completed work.

**Per-fit-level generation** — five explicit prompt variants rather than random sampling. Random generation produces a bimodal distribution (mostly "good" with some "poor") and never reaches "Mismatch" at meaningful frequency. Structured generation gives full control over label balance.

**Rule-based labeler, not LLM-based** — the six failure metrics are deterministic, instant, and don't consume tokens. The LLM judge (`--enable-llm-judge`) is additive — it catches subtle quality issues the rules miss, but the rules gate schema correctness first. This keeps the pipeline runnable on a free Groq tier.

**strategy_used + latency_ms in API responses** — callers can alert on latency regression or distinguish `rule_based` from `rule_based+llm_judge` paths without parsing logs.

---

## At Scale

At org scale, any AI team training on synthetic data faces the same governance question: how do you know your synthetic distribution matches the real one? This pipeline operationalizes a validation-first answer — every pair is independently scored by six rule-based metrics before it enters the training corpus, failed pairs are corrected and re-scored rather than discarded, and the correction loop's before/after delta is tracked across runs. The pattern — generate → validate schema → label failure modes → correct with error context — applies to any LLM-generated training corpus regardless of domain. A team building customer-intent training data, legal-clause classifiers, or code-review datasets runs the same four phases against a different schema and a different labeler.

---

## Quick Start

```bash
cp .env.example .env   # add GROQ_API_KEY
make bootstrap         # uv sync --all-extras
make test              # 41 tests, ~10 seconds, no API calls
make generate          # run the full pipeline (10 jobs × 5 fit levels)
make serve             # FastAPI on :8000 — interactive docs at /docs
```

See [docs/tradeoffs.md](docs/tradeoffs.md) for design decisions and [docs/failures.md](docs/failures.md) for known failure modes.

**Blog post:** [docs/blog_post.md](docs/blog_post.md)

---

## Related Projects

| Repo | Relationship |
|---|---|
| [llm-utils](../llm-utils) | Shared LLM client with retry/backoff used in generation + correction |
| [synthetic-data-diy](../synthetic-data-diy) | Same pipeline pattern applied to home DIY repair Q&A |
