# Design and Tradeoffs

---

## Jaccard over Cosine for Skill Overlap

Skill matching is a set membership problem: does the resume have the required skill or not? Cosine similarity on embeddings conflates "Python" with "Python developer" or even "Rust" (both are programming languages), blurring the membership signal. Jaccard on normalized skill strings gives a crisp 0/1 membership test per skill, with a continuous ratio across the full set.

Tradeoff: Jaccard misses synonyms ("ML" vs "machine learning"). The `_normalize_skill()` function handles the most common cases via lowercase, version stripping, and suffix stripping. Adding embedding-based synonym resolution would improve recall at the cost of making scores non-deterministic across embedding model versions.

---

## Incremental JSONL Checkpointing

Each generated item is written to JSONL immediately after LLM completion, not batched at phase end. A crash or rate-limit trip loses at most one item. `--resume` works by re-reading all existing records and skipping already-completed (job_id, fit_level) combinations: O(n) startup cost for large runs.

Tradeoff: JSONL files are append-only and cannot be updated in place. Acceptable at expected dataset sizes (hundreds to low thousands of items).

---

## Circuit Breaker at 2 Consecutive 429s

Two consecutive 429 errors halt generation. At 1, a transient spike would kill a run unnecessarily. At 3+, the pipeline accumulates retries with backoff before stopping, adding minutes of dead time. Groq's rolling window resets in ~60 seconds, so 2 failures is enough to detect a real rate-limit event.

---

## LLM Judge is Opt-In

The rule-based labeler (Phase 3) runs entirely offline and is deterministic. Adding an LLM judge call per pair doubles latency and costs ~$0.001/pair. Most use cases don't need both signals: the binary gates from the rule-based labeler are sufficient for dataset quality. The judge is reserved for nuanced hallucination detection or awkward language assessment beyond the keyword heuristics.

---

## Correction Loop Re-Validates After Fixing

After the LLM corrects an invalid pair, the corrected pair goes back through schema validation before acceptance. This catches corrections that introduce new violations (e.g., fixing a missing skill by hallucinating a non-existent company). An extra validation pass per correction adds latency. Trusting the LLM's correction without re-checking produces silent schema violations downstream.

---

## Overlap Retry Loop at Generation Time

After generating each resume, Jaccard overlap is computed against required skills. If the result falls outside the fit level's target range, the generation is retried up to 3 times. This is the gate that enforces fit level targeting at generation time rather than post-hoc filtering. Without it, the LLM defaults to plausible-looking resumes for every fit level (Mismatch pairs averaged Jaccard 0.582 in early runs).

---

## API Response Includes strategy_used and latency_ms

Every `/review-resume` response includes `strategy_used` (rule_based vs rule_based+llm_judge) and `latency_ms`. Callers can alert on latency regression or distinguish serving paths without parsing logs. This follows the same observability-as-first-class-design pattern as observable-recommender's `retrieval_source` field.
