# Why career_changer Resumes Failed 2× More Often: Lessons from a Synthetic Resume Coaching Pipeline

Picture a hiring manager reviewing 500 resumes. Most fail immediately — wrong skills, seniority mismatch, buzzword-dense summaries with nothing behind them. Building an AI system that catches those failures requires training data that *actually has* those failure modes built in. That's the hard part.

This post documents a 4-phase pipeline that generates synthetic resume-job pairs with controlled fit levels, validates them structurally, labels them for 6 failure modes, and corrects failures through iterative LLM re-prompting. It covers two runs — a weak model baseline and a stronger model with a generation-time quality gate — and what changed between them.

---

## The Pipeline

```
LLM Generation
 └─ Schema Validation     (Pydantic — structure + format rules)
     └─ Failure Labeling  (6 quality dimensions per resume-job pair)
         └─ Correction Loop  (data-driven retry on failed records)
```

**What it generates:** 50 job descriptions across diverse industries, 5 resumes per job at controlled fit levels (excellent, good, partial, poor, mismatch), across 5 writing templates (formal, casual, technical, achievement_focused, career_changer).

**Evaluation stack:** Jaccard similarity, experience mismatch, seniority mismatch, missing core skills, hallucinated skills, awkward language — all computed per pair by a rule-based labeler.

---

## Two Runs

| | Run 1 | Run 2 |
|---|---|---|
| Model | `llama-3.1-8b-instant` | `gpt-4o-mini` |
| Generation quality gate | None | Overlap retry loop (≤3 attempts) |
| Jobs | 50 | 50 |
| Pairs | 198 | 250 |
| Schema validation rate | 100% | 100% |
| Quality pass rate | 61.1% | 31.6% |
| Mismatch avg Jaccard | 0.582 | **0.000** |

The schema validation rate is identical. Everything else differs.

---

## Finding 1: A Higher Pass Rate Isn't Better

Run 1 scored 61.1% quality pass rate. Run 2 scored 31.6%. At first glance this looks like a regression. It's the opposite.

The pass rate measures how many pairs correctly represent their intended fit level. With `llama-3.1-8b`, "mismatch" pairs averaged 0.582 Jaccard overlap — meaning the model ignored the instruction to generate a mismatched resume and produced a reasonable partial fit instead. Those pairs were failing silently: structurally valid, semantically wrong. Many of them scored well enough on the labeler to pass.

With `gpt-4o-mini` and the retry loop, "mismatch" pairs average 0.000 Jaccard. They fail the labeler correctly — by design. Poor and mismatch pairs are *supposed* to fail. A pass rate of 31.6% with five fit levels means excellent and good pairs are passing and the rest are failing as intended.

**The rule:** a higher pass rate from a weaker model often means the fit level targeting is broken, not that the data is better. Evaluate labeler pass rate per fit level, not overall.

---

## Finding 2: The Retry Loop Fixed Mismatch — Completely

The central problem in Run 1: LLMs optimize for coherence. A plausible-sounding resume inherently tends toward reasonable skill overlap. "Generate a mismatch resume" is an instruction that works against the model's learned behavior.

Avg Jaccard by fit level, both runs:

| Fit Level | Run 1 (llama-3.1-8b) | Run 2 (gpt-4o-mini + retry) | Target |
|---|---|---|---|
| excellent | 0.916 | **0.979** | ≥ 0.80 |
| good | 0.805 | **0.745** | 0.60–0.80 |
| partial | 0.766 | **0.548** | 0.40–0.60 |
| poor | 0.627 | **0.244** | 0.20–0.40 |
| mismatch | 0.582 | **0.000** | < 0.20 |

Run 1 missed every target below "good". Run 2 hits all five.

The fix was a post-generation quality gate: after each resume is generated, compute Jaccard against the job's required skills. If the overlap falls outside the fit level's target range, re-prompt with a correction message (up to 3 retries). Without this gate, the LLM defaults to generating competent candidates regardless of fit level instruction. See [docs/correction_loop_proof.md](correction_loop_proof.md) for the correction loop results.

**The rule:** "generate a poor fit resume" is not sufficient. You need a verification step that checks whether the generated resume actually satisfies the fit constraint, with a correction signal when it doesn't.

---

## Finding 3: Template Bias Narrowed But Didn't Disappear

Run 1 finding: `career_changer` failed at more than twice the rate of `technical` (55.6% vs 42.4%). Run 2 with a stronger model:

| Template | Run 1 (llama-3.1-8b) | Run 2 (gpt-4o-mini) |
|---|---|---|
| `career_changer` | 55.6% | 70.9% |
| `technical` | 42.4% | 61.4% |
| `formal` | 36.6% | 68.8% |
| `achievement_focused` | 36.6% | 70.8% |
| `casual` | 21.1% | 71.4% |

Two things happened. The 2× gap narrowed to 1.15× — `career_changer` no longer stands out. And overall failure rates rose across all templates. Both are explained by the retry loop.

The retry loop fixed fit level targeting, which means poor and mismatch pairs now correctly fail. With Run 1, those pairs were passing at inflated rates (0.582 overlap for "mismatch"). Now they fail correctly, which raises the failure rate for every template. The templates converge because the per-template variation in Run 1 was partly noise from broken fit level generation.

The `career_changer` gap narrowing is significant: it suggests part of the original 2× bias was the 8B model struggling to simultaneously honor a writing style constraint and a fit level constraint. A stronger model handles both better. The residual gap (70.9% vs 61.4%) reflects genuine task difficulty — `career_changer` resumes are structurally harder to generate because they require intentional skill gaps from someone with transferable-but-not-direct experience.

**The rule:** template bias is real but partially model-dependent. Separate the model capacity effect from the task difficulty effect before drawing conclusions about which templates need prompt fixes.

---

## Finding 4: Dominant Failure Mode Shifted Once Fit Levels Were Fixed

Failure rates by mode, both runs:

| Failure Mode | Run 1 (llama-3.1-8b) | Run 2 (gpt-4o-mini) |
|---|---|---|
| `missing_core_skill` | 11.6% | **43.2%** |
| `seniority_mismatch` | **19.7%** | 26.0% |
| `low_skills_overlap` | 14.6% | 56.0% |
| `experience_mismatch` | 3.0% | 12.8% |
| `awkward_language` | 0.0% | 5.6% |
| `hallucinated_skill` | 0.5% | 0.8% |

In Run 1, seniority mismatch led (19.7%). In Run 2, missing core skill dominates at 43.2%. This isn't a new problem — it's the same problem becoming visible once the bigger problem (broken fit level targeting) is fixed.

When mismatch pairs have 0.582 Jaccard, they're not missing core skills — they accidentally match enough skills to avoid that flag. Fix the overlap and the missing core skill flag fires correctly on poor and mismatch pairs. The 43.2% rate is expected: poor fit resumes intentionally exclude top required skills.

`awkward_language` appearing at 5.6% (up from 0%) is a side effect of `gpt-4o-mini` generating more naturally-structured resumes — longer summary sections with more varied vocabulary occasionally trip the buzzword density detector. Not a quality problem; a detector calibration note.

**The rule:** fixing one failure mode can unmask others. After each prompt or model change, re-run the full labeler to see what was previously hidden.

---

## Finding 5: Seniority Mismatch Persists Across Both Models

Seniority mismatch is 19.7% in Run 1 and 26.0% in Run 2 — it increased with the stronger model. The cause is the same in both runs: the LLM defaults to generating mid-level candidates. An "excellent fit" for a senior role needs a senior candidate; the model generates a plausible-sounding mid-level one instead.

The fix is explicit: add a seniority constraint to every generation prompt.

```
The candidate's seniority level must be {target_seniority}.
If the job requires Senior, generate a candidate who is demonstrably Senior-level.
Do not generate a candidate who appears qualified for a different seniority level.
```

The retry loop handles overlap. Seniority requires the same pattern: generate, check, retry with a correction message if the inferred seniority doesn't match the target. This is not yet implemented — it's the next iteration. See [docs/iteration_log.md](iteration_log.md) for the documented change history.

---

## Takeaways

**1. A higher pass rate from a weaker model means fit level targeting is broken.** Run 1's 61.1% looked good. Run 2's 31.6% is correct. Check overlap by fit level, not overall.

**2. Verification beats instruction.** "Generate a mismatch resume" doesn't work reliably. Generate, compute Jaccard, retry with a correction if it fails. Mismatch went from 0.582 to 0.000.

**3. Template bias is partially model-dependent.** The career_changer 2× gap narrowed to 1.15× with a stronger model. Some of it was model capacity, not task difficulty.

**4. Fixing fit level targeting unmasks the next failure mode.** Missing core skill jumped from 11.6% to 43.2% once overlap was correct. Run the full labeler after every change.

**5. Seniority mismatch is persistent.** 19.7% → 26.0% across models. Requires the same verification-loop approach applied to overlap.

**6. Awkward language detection needs calibration for LLM-generated data.** 0% → 5.6% isn't a quality regression — it's a detector sensitivity issue when the model writes longer, more varied summaries.

---

## Run It Yourself

```bash
git clone git@github.com:selizondo/synthetic-data-resume-coach.git
cd synthetic-data-resume-coach

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

cp .env.example .env
# Set LLM_API_KEY and LLM_MODEL in .env (default: OpenAI gpt-4o-mini)

make bootstrap    # install all deps
make test         # 57 tests, ~10s, no API calls
make generate     # 10 jobs × 5 fit levels = 50 pairs
make serve        # FastAPI at 127.0.0.1:8000 — interactive docs at /docs
```

For the full 50-job run:

```bash
python -m src.main --num-jobs 50 --no-heatmaps

# Resume a run interrupted mid-way
python -m src.main --phase 2-4 --resume <run_label>

# Run label quality analysis on a completed run
python -m src.main --eval-quality --resume <run_label>
```

Output lands in `data/`. Each phase writes its own JSONL files stamped with the run label — see the README for the full output structure. Pipeline summaries in `data/pipeline_summary_<run_label>.json` give per-phase timing and aggregate statistics. The labeler accuracy is verified in [docs/spot_check.md](spot_check.md).
