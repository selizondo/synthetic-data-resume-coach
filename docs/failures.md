# Failure Scenarios

Documented failure modes with detection mechanisms and fallback behavior.

---

## Failure 1: LLM Rate-Limit Exhaustion Mid-Run

### What breaks
The pipeline generates 40+ resume pairs per run. A transient TPM spike or daily quota exhaustion mid-batch causes all remaining items to fail with 429 errors.

### Why it matters
Without protection, a rate-limit error loses all in-flight work and the user must restart the entire batch from scratch.

### Detection mechanism
`llm_utils.client` parses the provider's `retry-after` header. If the wait is ≤300s (TPM throttle), it sleeps and retries. If the wait exceeds the threshold (daily quota), it raises `RuntimeError` immediately with a clear message.

### Fallback behavior
JSONL incremental checkpointing: each generated item is written immediately after completion. On restart, `--resume <run_label>` reads existing JSONL records and skips already-completed `(job_id, fit_level)` pairs. At most one item is lost per crash.

---

## Failure 2: LLM Correction Introduces a New Schema Violation

### What breaks
Phase 4 sends invalid resume pairs to an LLM for correction. The LLM fixes the reported issue but introduces a new violation (e.g., removes a required field while rewording).

### Why it matters
Accepting the LLM's corrected output without re-validating would silently pass malformed data downstream into the training dataset.

### Detection mechanism
After each correction LLM call, the output is put back through the same Pydantic schema validator used in Phase 2. A new violation triggers another correction attempt (up to `max_correction_retries`). Items that still fail after all retries are logged as `correction_failed` and excluded.

### Fallback behavior
The item is dropped from the dataset and its `trace_id` is logged with failure reason. The pipeline continues with remaining items.

---

## Failure 3: Category Distribution Imbalance

### What breaks
If the LLM overproduces one fit level or writing template relative to others, the dataset skews toward one profile type. A model trained on this data would be disproportionately good at one category and weak at others.

### Why it matters
Downstream fine-tuning quality depends on balanced representation across all fit levels and template types.

### Detection mechanism
Phase 1 generates exactly one resume per fit level per job via structured prompts: imbalance is prevented at generation time, not detected after. The `by_template` and `by_fit_level` breakdowns in `pipeline_summary_{run_label}.json` → `phases.labeling` let you verify coverage after the run.

### Fallback behavior
If a fit level or template is underrepresented, re-run Phase 1 with `--resume <run_label>` to generate missing pairs without regenerating existing ones.

---

## Failure 4: Near-Duplicate Resume-Job Pairs

### What breaks
Two pairs share the same job but slightly different resume phrasing. They pass structural validation but inflate the dataset with near-identical training examples.

### Why it matters
Near-duplicate training pairs cause a fine-tuned model to memorize specific phrasings rather than learning generalizable patterns.

### Detection mechanism
Currently not detected: deduplication is not implemented. This is a known gap. Each job generates exactly one resume per fit level (5 pairs per job), so within-job duplication can't happen. Cross-job near-duplication is possible but low-probability at dataset sizes ≤500 pairs.

### Fallback behavior
None at pipeline level. Embedding-based near-dedup (cosine similarity threshold) was cut to avoid added complexity and API cost at this dataset size. Manual inspection of the final JSONL is recommended before using the dataset for fine-tuning.
