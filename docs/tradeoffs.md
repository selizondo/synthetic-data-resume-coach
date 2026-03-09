# Design Decisions and Tradeoffs

## Jaccard over cosine for skill overlap

Skill matching is a set membership problem: does the resume have the required skill or not? Cosine similarity on embeddings would conflate "Python" with "Python developer" or even "Rust" (both are languages), blurring the signal we want. Jaccard on normalized skill strings gives a crisp 0/1 membership test per skill, with a continuous overlap ratio across the full set. The tradeoff: Jaccard misses synonyms ("ML" vs "machine learning") — the `normalize_skill()` function handles the most common cases via substring stripping.

## Incremental JSONL checkpointing

Each generated item is written to JSONL immediately after LLM completion, not batched at the end of the phase. This means a crash or rate-limit trip loses at most one item. The tradeoff: JSONL files are append-only and can't be easily updated in place — `--resume` works by re-reading all existing records and skipping already-completed (job_id, fit_level) combinations, which adds O(n) startup cost for large runs.

## Circuit breaker threshold = 2

Two consecutive 429 errors trigger the breaker and halt generation. At 1, a transient spike would kill a run unnecessarily. At 3+, the pipeline would rack up 3 retries with backoff before stopping, adding minutes of dead time. Groq's rolling window resets in ~60 seconds, so 2 failures is enough to detect a real rate-limit event without wasting time.

## LLM judge is opt-in (`--enable-llm-judge`)

The rule-based labeler (Phase 3) runs entirely offline and is deterministic. Adding an LLM judge call per pair doubles latency and costs ~$0.001/pair at current Groq pricing. Most use cases don't need both signals — the binary gates from the rule-based labeler are sufficient for dataset quality. The judge is reserved for cases where nuanced hallucination detection or awkward language assessment is needed beyond the keyword heuristics.

## Correction loop re-validates after fixing (Phase 4)

After the LLM corrects an invalid pair, it goes back through schema validation before being accepted. This catches cases where the correction itself introduced a new schema violation (e.g., fixing a missing skill by hallucinating a non-existent company). The tradeoff: an extra validation pass per correction adds latency. The alternative — trusting the LLM's correction without re-checking — produces silent schema violations downstream.
