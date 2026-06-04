# Iteration Log

Every threshold or configuration change is recorded here with the metric that motivated it, what changed, and whether it was kept.

---

| Date | Component | Change | Before | After | Delta | Decision |
|---|---|---|---|---|---|---|
| 2026-05-02 | Generator | Switched LLM from Groq `llama-3.1-8b-instant` to OpenAI `gpt-4o-mini` | Schema validation ~82%, frequent missing-field errors on `skills.proficiency_level` and `experience.achievements` | Schema validation 100% across 250 pairs | +18pp schema pass rate | Keep — 8b model generated structurally inconsistent resumes; gpt-4o-mini reliably followed the Pydantic schema contract |
| 2026-05-28 | Generator | Added post-generation overlap retry loop — after each resume is generated, compute Jaccard against required skills; retry up to 3× if overlap falls outside the fit level's target range | Excellent-fit resumes averaged Jaccard ~0.65 (LLM defaulted to "reasonable" overlap regardless of fit level instruction) | Excellent avg = 0.979, Good avg = 0.745, Partial avg = 0.548, Poor avg = 0.244, Mismatch avg = 0.000 — all within spec ranges | Excellent +0.33, Mismatch corrected from ~0.15 to 0.00 | Keep — without the retry gate the fit level distribution collapsed toward "good" regardless of prompt instructions |
| 2026-05-28 | Labeler | Added `_normalize_skill()` — lowercase conversion, strip version numbers (`3.10`, `v2`), strip suffixes (`.js`, `developer`, `engineer`) before Jaccard calculation | "Python 3.10", "Python", and "python developer" counted as three distinct skills → Jaccard artificially low across all fit levels | All three normalize to `python` → avg Jaccard 0.50 across 250 pairs; labeler pass rate stable across runs | Avg Jaccard +~0.15 (estimated from early runs with raw strings) | Keep — without normalization the overlap metric doesn't reflect actual skill coverage |
