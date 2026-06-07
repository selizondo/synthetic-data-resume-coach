# Synthetic Data Resume Coach

![Tests](https://github.com/selizondo/synthetic-data-resume-coach/actions/workflows/ci.yml/badge.svg)

The 8B model passed quality checks at 61.1%. The stronger model passed at 31.6%. The lower number is the correct one.

The 8B model ignored fit level instructions and generated plausible-looking resumes for every fit level. Mismatch pairs averaged Jaccard 0.582 instead of near 0: the "mismatches" were actually decent candidates. The labeler correctly flagged most of them as passing, because they were. The stronger model with a generation-time overlap retry loop produced real mismatches (avg Jaccard 0.000). Those fail the labeler as intended.

This is the measurement that matters: not whether the pass rate is high, but whether the distribution matches what you asked for.

**Stack:** Python · OpenAI · instructor · FastAPI · Pydantic · llm-utils

## Related Projects

1. [synthetic-data-diy](https://github.com/selizondo/synthetic-data-diy) — same generate-validate-label-correct pattern, different domain
2. [llm-utils](https://github.com/selizondo/llm-utils) — shared LLM client used by generation and correction

*Companion post: [Why career_changer Resumes Failed 2x More Often](docs/blog_post.md) — fit-level distribution and measurement*

---

## Results

50-job run (gpt-4o-mini + overlap retry loop), 250 pairs (5 fit levels per job):

| Signal | Value |
|--------|-------|
| Schema validation rate | 100% (instructor enforces schema at generation time) |
| Overall labeler pass rate | 31.6% |
| Dominant failure mode | Missing core skill: 43.2% |
| Jaccard by fit level | Excellent=1.00, Good=0.67, Partial=0.43, Poor=0.25, Mismatch=0.00 |
| Manual spot-check agreement | 10/10 (100%) |
| Correction loop success | 10/10 on injected schema errors, 0 normal runs (by design) |
| Test suite | 57 tests, fully offline |

## How It Works

### One resume per fit level, with a generation-time gate

Each job generates exactly one resume per fit level (Excellent through Mismatch). Without explicit instructions, an LLM defaults to generating plausible resumes at every level: Mismatch pairs averaged Jaccard 0.582 in early runs. The overlap retry loop computes Jaccard after generation and retries up to 3 times if overlap falls outside the fit level's target range. After the gate: Excellent=0.979, Mismatch=0.000.

### Rule-based labeling: 6 metrics, no LLM required

Jaccard skill overlap, experience mismatch, seniority mismatch, missing core skill, hallucinated skill, awkward language density. All deterministic, computed offline, zero API cost. The LLM judge is opt-in and additive: it catches subtle quality issues the rules miss but does not replace them.

### Correction loop uses Pydantic errors as the feedback signal

Invalid pairs are re-prompted with their exact Pydantic error messages (field path, error type, invalid value). This gives the LLM precise context to fix the issue without guessing. 100% correction on the first attempt in the proof-of-concept run. In normal runs, the correction loop does not fire: `instructor` prevents schema-invalid records from being generated in the first place.

## Go Deeper

| Audience | Doc |
|----------|-----|
| Running the code | [Setup and Usage](docs/setup.md) |
| Engineering decisions | [Design and Tradeoffs](docs/engineering.md) |
| What breaks and why | [Failure Modes](docs/failures.md) |
| Proof of correctness | [Evidence](docs/evidence.md) |
