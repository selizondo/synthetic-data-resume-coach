# Failure Scenarios

Documented failure modes with detection mechanisms. Tests live in `tests/test_failure_scenarios.py`.

---

## Failure 1: LLM Rate-Limit Exhaustion Mid-Run

### What breaks
The pipeline generates 40+ resume pairs per run at Groq's free tier. A transient TPM spike or daily quota exhaustion mid-batch causes all remaining items to fail with 429 errors.

### Why it matters
Without protection, a rate-limit error loses all in-flight work and the user must restart the entire batch from scratch.

### Detection mechanism
`llm_utils.client` parses the provider's `retry-after` header. If the wait is ≤300s (TPM throttle), it sleeps and retries. If the wait exceeds `TPD_THRESHOLD = 300.0s` (daily quota), it raises `RuntimeError` immediately with a clear message: "Daily token quota exhausted — retry after UTC midnight."

### Fallback behavior
JSONL incremental checkpointing: each generated item is written immediately after completion. On restart, the pipeline reads existing JSONL records and skips already-completed `(job_id, fit_level)` pairs. At most one item is lost per crash.

### Reproduction
Run with a model that has a known quota limit and exhaust it. The pipeline logs `[rate limit] waiting Ns (attempt X/3)...` for transient limits and raises on daily exhaustion.

---

## Failure 2: LLM Correction Introduces a New Schema Violation

### What breaks
Phase 4 sends invalid resume pairs to an LLM for correction. The LLM fixes the reported issue (e.g., a too-short `skill_gap_explanation`) but introduces a new violation (e.g., removes a required field while rewording).

### Why it matters
Accepting the LLM's corrected output without re-validating would silently pass malformed data downstream into the training dataset.

### Detection mechanism
After the correction LLM call, the output is put back through the same Pydantic schema validator used in Phase 1. A new violation triggers a second correction attempt (up to `max_correction_retries`). Items that still fail after all retries are logged as `correction_failed` and excluded.

### Fallback behavior
The item is dropped from the dataset and its `trace_id` is logged with failure reason. The pipeline continues with the remaining items.

---

## Failure 3: Category Distribution Imbalance

### What breaks
If the LLM overproduces one resume category (e.g., `career_changer`) relative to others, the dataset skews toward one profile type. A fine-tuned model trained on this data would be disproportionately good at one category and weak at others.

### Why it matters
Downstream fine-tuning quality depends on balanced representation across all fit levels and template types.

### Detection mechanism
`_check_category_distribution()` in Phase 2 computes per-category fractions. Any category below `_MIN_CATEGORY_FRACTION = 0.20` triggers a warning and the result is flagged as `distribution_imbalance` in the pipeline summary.

### Fallback behavior
The pipeline does not halt — it reports the imbalance in the Phase 2 summary and continues. The caller can inspect `pipeline_summary.json` → `phases.validation.resume_summary.category_fractions` and re-run generation with a targeted prompt to fill underrepresented categories.

---

## Failure 4: Deduplication Silently Removes Semantically Similar Items

### What breaks
`_run_dedup()` removes exact-match duplicates (case-normalized question strings). If the LLM generates two items with the same resume template and slightly different wording, they pass dedup but inflate the dataset with near-duplicate pairs.

### Why it matters
Near-duplicate training pairs cause the fine-tuned model to memorize specific phrasings rather than learning generalizable patterns.

### Detection mechanism
Currently not detected — the dedup pass is exact-match only. The known gap is documented here and in `docs/tradeoffs.md`. The fix is embedding-based near-dedup (e.g., cosine similarity threshold), which was explicitly cut to avoid the added complexity and API cost at this dataset size.

### Fallback behavior
None — this is a known gap. Manual inspection of the final JSONL is recommended before using the dataset for fine-tuning.
