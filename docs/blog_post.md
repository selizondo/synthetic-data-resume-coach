# Why career_changer Resumes Failed 2× More Often: Lessons from a Synthetic Resume Coaching Pipeline

Picture a hiring manager reviewing 500 resumes. Most fail immediately — wrong skills, seniority mismatch, buzzword-dense summaries with nothing behind them. Building an AI system that catches those failures requires training data that *actually has* those failure modes built in. That's the hard part.

This post documents a 4-phase pipeline that generates synthetic resume-job pairs with controlled fit levels, validates them structurally, labels them for 6 failure modes, and attempts to correct the ones that fail. The pipeline found a problem you won't anticipate: 100% of generated resumes passed Pydantic schema validation. 42% failed quality labels. And the `career_changer` writing template failed at more than twice the rate of the `technical` template — same LLM, same jobs, same instructions.

One thing to take away: why "structurally valid" and "actually usable" are different thresholds, and which failure mode matters most when you're trying to control fit level.

---

## The Pipeline

```
LLM Generation
 └─ Schema Validation     (Pydantic — structure + format rules)
     └─ Failure Labeling  (6 quality dimensions per resume-job pair)
         └─ Correction Loop  (data-driven retry on failed records)
```

**What it generates:** job descriptions across 50+ roles, resumes at 5 controlled fit levels (excellent, good, partial, poor, mismatch), across 5 writing templates (formal, casual, technical, achievement-focused, career-changer).

**Evaluation stack:** Jaccard similarity, experience mismatch, seniority mismatch, missing core skills, hallucinated skills, awkward language — all computed per pair.

**Two runs compared:**

| Model | Jobs | Pairs | Validation rate | Pass rate | Gen time |
|---|---|---|---|---|---|
| `llama-3.3-70b-versatile` | 6 | 12 | 100% | 83.3% | ~279 min |
| `llama-3.1-8b-instant` | 50 | 198 | 100% | 61.1% | ~83 min |

---

## Finding 1: 100% Validation Rate, 61% Pass Rate — These Are Different Things

Both runs validated 100% of generated records. Zero schema failures. The 8B run still scored 61.1% overall quality pass rate.

Structural validation answers: *does this conform to the schema?* Quality labeling answers: *does this resume actually behave the way it's supposed to for this fit level?*

These diverge because LLMs are excellent at producing structurally valid output. Instructor + Pydantic virtually eliminates schema failures. But producing a resume that *correctly represents* a "poor fit" for a specific job — intentional skill gaps, seniority misalignment, controlled overlap — is a harder semantic task that schema rules can't enforce.

**The rule:** schema validation is a floor, not a ceiling. 100% validation rate with 39% failure rate means your generator reliably produces well-formed data that often fails at what it's supposed to do. Evaluate fitness separately from structure.

---

## Finding 2: career_changer Fails 2× More Often — and It's Structural, Not Random

Failure rates by writing template (8B model, 198 pairs):

| Template | Pairs | Failure Rate |
|---|---|---|
| `career_changer` | 45 | **55.6%** |
| `technical` | 33 | 42.4% |
| `formal` | 41 | 36.6% |
| `achievement_focused` | 41 | 36.6% |
| `casual` | 38 | **21.1%** |

The `career_changer` template asks the LLM to generate a resume for someone transitioning from a different field. That means intentionally generating skill gaps, limited direct experience, and transferable skills that partially but not fully match the job. The LLM struggles with this — it defaults to producing competent candidates.

The `technical` template landing second-highest (42.4%) is notable: highly specific skill lists make it easier for the model to produce a "wrong" result by including a recognizable but mismatched technology. `casual` performs best because vague, conversational phrasing is harder to falsify against a structured job description.

The 70B model shows the same directional pattern (career_changer 33% vs. technical 20%) at higher overall quality. The gap narrows but doesn't close with a more capable model — suggesting the challenge is the task itself, not the model's capacity.

**The rule:** templates that require the LLM to be *deliberately bad* at matching a job are harder to control than templates that produce good candidates. If your evaluation depends on diverse fit levels, the failure rate will be template-specific — not uniform across writing styles.

---

## Finding 3: The LLM Can't Reliably Produce "Mismatch" Resumes

Controlled fit level generation is the core design challenge. The pipeline targets 5 fit levels, with "mismatch" meaning less than 20% skill overlap. Actual results:

| Fit Level | 8B Avg Overlap | 70B Avg Overlap | Target |
|---|---|---|---|
| excellent | 0.916 | 0.867 | ≥ 80% |
| good | 0.805 | 1.000 | 60–80% |
| partial | 0.766 | 0.833 | 40–60% |
| poor | 0.627 | 0.600 | 20–40% |
| mismatch | **0.582** | **0.300** | < 20% |

The 70B model gets "mismatch" to 0.30 average overlap — outside the target (< 0.20) but directionally correct. The 8B model produces 0.58 average overlap for "mismatch" pairs. The model intended to generate a resume with almost no skill overlap and produced one that's a reasonable partial fit.

This is the central limitation: LLMs optimize for coherence and helpfulness during training. A plausible-sounding resume inherently tends toward reasonable skill match. Generating *intentionally poor* resumes is an instruction that works against the model's learned behavior.

**The rule:** the harder the fit level is to fake, the more you need explicit negative examples or stricter skill-exclusion instructions in the prompt. "Generate a poor fit resume" is not sufficient. You need: "Do not include any of these skills: {required_skills}. Do not match the required experience level of {level}."

---

## Finding 4: Seniority Mismatch Is the Dominant Failure Mode

Failure rates by mode (8B model, 198 pairs):

| Failure Mode | Rate |
|---|---|
| `seniority_mismatch` | **19.7%** |
| `low_skills_overlap` | 14.6% |
| `missing_core_skill` | 11.6% |
| `experience_mismatch` | 3.0% |
| `hallucinated_skill` | 0.5% |
| `awkward_language` | **0.0%** |

Seniority mismatch (19.7%) leads all failure modes by a clear margin. The same pattern holds in the 70B run (16.7%). Two models, consistent result — this is a generation behavior, not a model artifact.

The cause: the LLM tends to generate mid-level candidates regardless of fit level instruction. An "excellent fit mismatch" still needs a plausible-sounding candidate, and plausible defaults to mid-level. Generating an entry-level candidate for a senior role — or vice versa — requires the model to produce something that sounds underqualified or overqualified, which feels incoherent from a generation standpoint.

`awkward_language` scored 0.0% across all templates. LLMs don't produce buzzword-heavy AI-generated text when instructed to write as a human candidate. This failure mode may not be useful for LLM-generated synthetic data — it's designed for detecting real human resumes, not controlled synthetic generation.

**The rule:** add an explicit seniority constraint to every generation prompt: "The candidate's seniority level must be {target_level}. If the job requires Senior, generate a Mid-level candidate." Without this, seniority mismatch will be the dominant failure mode regardless of fit level.

---

## Finding 5: Model Choice Trades Quality for Speed — But Not Proportionally

| Model | Pairs generated | Generation time | Pass rate | Cost |
|---|---|---|---|---|
| `llama-3.3-70b-versatile` | 12 | ~279 min | 83.3% | ~$0.54 |
| `llama-3.1-8b-instant` | 198 | ~83 min | 61.1% | ~$0.008 |

The 70B model produces ~22pp better pass rates. It also takes ~55× longer per pair (279 min / 12 pairs vs. 83 min / 198 pairs) and costs ~68× more.

The 279 minutes is not inference time — it's rate-limit throttling on Groq's free tier. The 70B model triggers more aggressive rate limiting than the 8B. The same quality gap at less cost is available by running 70B at lower volume or on a paid tier.

For iterative pipeline development, 8B at ~$0.008/run is the right choice. Switch to 70B for final evaluation once generation prompts are stable. The 22pp quality gap is worth paying for validation, not experimentation.

---

## Practical Guide: Fixing the Top 3 Failure Modes

### Fix seniority mismatch (19.4%)

Add explicit level constraint to the generation prompt:
```
Seniority level: {target_seniority}
IMPORTANT: The candidate's demonstrated experience level must be {target_seniority}.
Do not generate a candidate who appears qualified for a different seniority level.
```

### Fix mismatch fit level overlap (actual: 0.58, target: < 0.20)

Add explicit skill exclusion:
```
This is a MISMATCH resume. The candidate must NOT have these required skills: {required_skills[:3]}.
Replace required skills with unrelated skills from a different field.
Target Jaccard similarity: < 0.20.
```

### Fix career_changer failure rate (64.3%)

The template conflates two tasks: write a career-changer resume AND match a specific fit level. Separate them:
1. Generate the base career-changer persona (industry, years, transferable skills)
2. Then apply fit-level constraints as a second prompt pass

One-shot generation of both simultaneously overloads the model's ability to honor both constraints at once.

---

## Takeaways

**1. Structural validation and quality labeling are different evaluations.** 100% schema pass rate is a floor. 61% quality pass rate is the actual signal. Run both.

**2. Templates that require intentional failure are the hardest to generate.** `career_changer` (56% failure) vs. `casual` (21% failure). The LLM's helpfulness bias works against you when you need bad candidates.

**3. The LLM can't reliably produce mismatch resumes without explicit exclusions.** "Generate a poor fit" is insufficient. Specify which skills to exclude and which seniority level to misalign with.

**4. Seniority mismatch is the dominant failure mode across models.** 19.7% (8B) and 16.7% (70B). Add explicit seniority instructions or it will stay the top failure mode regardless of model size.

**5. Use a smaller model for iteration, a larger model for validation.** 8B at $0.003/run for prompt development. 70B for the final evaluation run where quality numbers matter.

**6. Awkward language detection won't fire on LLM-generated data.** 0% across all templates. This failure mode is designed for human resumes — LLMs don't produce buzzword-dense text when instructed to write naturally.

---

## Run It Yourself

```bash
git clone git@github.com:selizondo/newline_stuff.git
cd newline_stuff/projects/synthetic_data_resume_coach

pip install -r requirements.txt
cp .env.example .env
# Set LLM_API_KEY and LLM_MODEL in .env

# Full 4-phase pipeline
python src/main.py --batch-label my-run

# Individual phases
python src/main.py --phase 1 --batch-label my-run   # generation
python src/main.py --phase 2 --batch-label my-run   # validation
python src/main.py --phase 3 --batch-label my-run   # labeling
python src/main.py --phase 4 --batch-label my-run   # correction

# View results across runs
python src/main.py stats
```

Results land in `data/output/<batch-label>/`. Each phase is independently re-runnable. Pipeline summaries in `data/pipeline_summary_*.json` give per-phase timing and aggregate statistics.
