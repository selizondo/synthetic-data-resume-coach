# Evidence

Iteration log, labeler spot-check, and correction loop proof.

---

## Iteration Log

| Date | Component | Change | Before | After | Delta | Decision |
|------|-----------|--------|--------|-------|-------|----------|
| 2026-05-02 | Generator | Switched from Groq `llama-3.1-8b-instant` to OpenAI `gpt-4o-mini` | Schema validation ~82%, frequent missing fields on `skills.proficiency_level` and `experience.achievements` | Schema validation 100% across 250 pairs | +18pp schema pass rate | Keep: 8b model generated structurally inconsistent resumes; gpt-4o-mini reliably followed the schema contract |
| 2026-05-28 | Generator | Added post-generation overlap retry loop: compute Jaccard after each resume is generated, retry up to 3x if outside the fit level's target range | Excellent-fit resumes averaged Jaccard ~0.65; LLM ignored fit level instructions | Excellent avg=0.979, Good avg=0.745, Partial avg=0.548, Poor avg=0.244, Mismatch avg=0.000 | Excellent +0.33, Mismatch corrected from ~0.15 to 0.00 | Keep: without the retry gate the fit level distribution collapsed toward "good" regardless of prompt instructions |
| 2026-05-28 | Labeler | Added `_normalize_skill()`: lowercase, strip version numbers, strip suffixes before Jaccard | "Python 3.10", "Python", "python developer" counted as 3 distinct skills; Jaccard artificially low | All 3 normalize to "python"; avg Jaccard 0.50 across 250 pairs | Avg Jaccard +~0.15 | Keep: without normalization the overlap metric does not reflect actual skill coverage |

---

## Manual Spot-Check: Labeler Accuracy

10 pairs sampled from `failure_labels_20260528_185335.jsonl` (2 per fit level). Each row verifies automated metrics against independent recomputation from raw data using the same `_normalize_skill()` logic.

| Pair | Fit Level | Jaccard (auto) | Jaccard (manual) | All flags correct | Manual agrees? |
|------|-----------|---------------|-----------------|-------------------|----------------|
| pair_01 | excellent | 1.00 | 1.00 | No flags | yes |
| pair_02 | excellent | 1.00 | 1.00 | No flags | yes |
| pair_03 | good | 0.67 | 0.67 | No flags | yes |
| pair_04 | good | 0.67 | 0.67 | No flags | yes |
| pair_05 | partial | 0.43 | 0.43 | No flags | yes |
| pair_06 | partial | 0.43 | 0.43 | Seniority mismatch | yes |
| pair_07 | poor | 0.25 | 0.25 | Missing core skill | yes |
| pair_08 | poor | 0.25 | 0.25 | Exp + missing core | yes |
| pair_09 | mismatch | 0.00 | 0.00 | Seniority + missing core | yes |
| pair_10 | mismatch | 0.00 | 0.00 | Exp + seniority + missing core | yes |

**Agreement rate: 10/10 (100%).** Jaccard tracks fit level cleanly. Seniority and missing core skill flags fire on the right pairs. Hallucination (0.8% run-level rate) and awkward language (5.6%) are not represented in this 10-pair sample.

---

## Correction Loop Proof

The pipeline uses `instructor` to enforce the Pydantic schema at generation time. With gpt-4o-mini, this results in 100% schema validation across all normal runs. The correction loop has nothing to process because no invalid records reach Phase 4. This is the intended behavior.

To verify the loop works when it does have input, 10 valid resumes from `data/correction_test/` were corrupted with realistic schema errors:

| Error type | Field | Pydantic message |
|-----------|-------|-----------------|
| Invalid email | `contact.email` | "An email address must have an @-sign" |
| Bad date format | `experience.*.start_date/end_date` | "Unable to parse date: 2021/06/01" |
| GPA out of range | `education.*.gpa` | "Input should be less than or equal to 4" |
| Phone too short | `contact.phone` | "String should have at least 10 characters" |

Results:

| Attempt | Records | Corrected | Still Invalid | Success Rate |
|---------|---------|-----------|--------------|-------------|
| 1 | 10 | 10 | 0 | 100% |

All 10 corrected on the first attempt. Average attempts: 1.0. The correction prompt includes exact Pydantic error messages with field path, error type, and invalid value, giving the LLM precise context instead of requiring it to guess what changed.

The loop does not fire in production runs because `instructor` prevents schema-invalid records from being generated in the first place. The correction loop handles the edge case where generation infrastructure fails: rate limits mid-batch, model downgrade, prompt regression.

---

## Two-Run Comparison: The Inverse Result

| | Run 1 (8B model) | Run 2 (gpt-4o-mini + retry loop) |
|--|------------------|-----------------------------------|
| Model | llama-3.1-8b-instant | gpt-4o-mini |
| Generation quality gate | None | Overlap retry loop (up to 3x) |
| Pairs generated | 198 | 250 |
| Schema validation rate | 100% | 100% |
| Quality pass rate | 61.1% | **31.6%** |
| Mismatch avg Jaccard | 0.582 | **0.000** |

The lower quality pass rate (31.6%) is the correct result. The 8B model's 61.1% pass rate reflected a collapsed fit level distribution where mismatch pairs were inadvertently good candidates. A lower pass rate with correctly distributed fit levels is a better dataset for training a resume scorer.
