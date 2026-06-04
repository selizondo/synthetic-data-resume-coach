# Correction Loop Proof

## Why the Loop Doesn't Fire in Normal Runs

The pipeline uses `instructor` to enforce the Pydantic schema at LLM output time. With `gpt-4o-mini`, this results in 100% schema validation across all runs — no invalid records reach Phase 4, so the correction loop has nothing to process. This is the correct behaviour: a validation-first pipeline that generates clean data is the goal. The correction loop is a safety net for when generation fails.

## Demonstrating the Loop Works

10 valid resumes from `data/correction_test/generated/resumes_20260602_232545.jsonl` were corrupted with realistic schema errors, then fed through `LLMCorrector` with `gpt-4o-mini` and `max_retries=3`.

### Errors Injected

| Error type | Field | Pydantic message |
|---|---|---|
| Invalid email | `contact.email` | `An email address must have an @-sign` |
| Bad date format | `experience.*.start_date`, `end_date` | `Unable to parse date: 2021/06/01` |
| GPA out of range | `education.*.gpa` | `Input should be less than or equal to 4` |
| Phone too short | `contact.phone` | `String should have at least 10 characters` |

### Correction Results

| Attempt | Records In | Corrected | Still Invalid | Success Rate |
|---|---|---|---|---|
| 1 | 10 | 10 | 0 | 100% |
| **Total** | **10** | **10** | **0** | **100%** |

All 10 corrected on the first attempt. Average attempts: 1.0.

The correction prompt includes the exact Pydantic error messages (field path, error type, invalid value), which gives the LLM precise context to fix the issue without guessing.

## Conclusion

The correction loop exceeds the >50% spec target when given records with fixable schema errors. The loop is not exercised in production runs because `instructor` prevents schema-invalid records from being generated in the first place — which is the intended design. The correction loop handles the edge case where generation infrastructure fails (rate limits mid-batch, model downgrade, prompt regression).
