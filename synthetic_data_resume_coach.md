# Mini-Project 2. AI-Powered Resume Coach: Synthetic Data Pipeline

## 🎯 Project Goal

Build a production-grade synthetic data pipeline that generates, validates, and analyzes resume-job description pairs using LLMs. Your system will act as an intelligent resume coach that can identify mismatches, detect quality issues, and provide actionable feedback.

**Core Challenge**: Create a system that not only generates realistic data but also understands what makes a resume "good" or "bad" for a specific job, then prove it works through rigorous evaluation.

***

## 🧠 The Problem Context

Hiring managers receive hundreds of resumes for each job posting. Most are poorly matched: wrong skills, mismatched experience levels, or filled with buzzwords and hallucinated claims.

Your task: Build an AI system that can:

* **Generate** realistic resume-job pairs with varying quality levels
* **Validate** that data follows strict structural rules
* **Analyze** why a resume fails to match a job (skills gap? seniority mismatch? hallucinations?)
* **Visualize** patterns in failures across different scenarios
* **Correct** invalid data through iterative LLM feedback
* **Serve** this intelligence via a REST API for real-time analysis

***

## 🔁 System Architecture Overview

Your pipeline should follow this high-level flow:

**1. Generation**: Generate job descriptions (with niche role detection) → Generate resumes with controlled fit levels per job → Create resume-job pairs with metadata

**2. Validation**: Schema validation (Pydantic models) → Error extraction and categorization → Save valid/invalid records separately

**3. Analysis**: Calculate failure metrics (Jaccard, experience gaps, etc.) → Optional LLM-as-Judge for subtle quality issues → Generate correlation matrices and heatmaps

**4. Correction (Optional)**: Feed validation errors back to LLM → Re-validate corrected outputs → Track correction success rates

**5. API Exposure**: POST /review-resume (analyze resume against job) → GET /health (health check) → GET /analysis/failure-rates (aggregate statistics)

***

## 📊 Success Metrics

Your system will be evaluated on these quantitative benchmarks:

### 1. **Data Generation Quality**

* Generate **50+ job descriptions** across diverse industries
* Generate **5-10 resumes per job** with controlled fit levels:
* Excellent fit (80%+ skill overlap)
* Good fit (60-80%)
* Partial fit (40-60%)
* Poor fit (20-40%)
* Complete mismatch (\<20%)

### 2. **Schema Validation Performance**

* **Target: >90% validation success rate** for generated data
* Detailed error categorization for failures:
* Missing required fields
* Type mismatches
* Format violations (email, dates, phone)
* Logical inconsistencies (end\_date before start\_date)

### 3. **Failure Detection Accuracy**

Your labeling system must calculate these metrics for every resume-job pair:

| ​ | Metric                  | Calculation Method                                          | Threshold       |
| - | ----------------------- | ----------------------------------------------------------- | --------------- |
| ​ | **Skills Overlap**      | Jaccard similarity:                                         | A ∩ B           |
| ​ | **Experience Mismatch** | Years gap or \<50% of required                              | Binary flag     |
| ​ | **Seniority Mismatch**  | Level difference (Entry=0, Mid=1, Senior=2, Lead=3, Exec=4) | >1 level = flag |
| ​ | **Missing Core Skills** | Absence of top-3 required skills                            | Binary flag     |
| ​ | **Hallucinated Skills** | Unrealistic claims (20+ "expert" skills, etc.)              | Binary flag     |
| ​ | **Awkward Language**    | Excessive buzzwords, AI patterns                            | Binary flag     |

### 4. **Correction Loop Effectiveness**

* **Target: >50% correction success rate** for invalid records
* Maximum 3 retry attempts per record
* Track: attempts per success, failure reasons

### 5. **API Performance**

* Response time: **\<2 seconds** (without LLM judge)
* Response time: **\<10 seconds** (with LLM judge enabled)
* All endpoints return valid JSON with proper error handling

***

## 🛠 Technical Requirements

### Required Technology Stack

* **Python 3.10+** - Core language
* **Pydantic** - Schema validation with detailed error reporting
* **Instructor** - Structured LLM outputs
* **LLM Provider** - Groq, OpenAI, or OpenRouter for generation
* **Pandas** - Data manipulation and analysis
* **Matplotlib/Seaborn** - Visualization generation
* **FastAPI** - REST API framework

### Optional Enhancements

* **Braintrust** - Evaluation tracking and logging
* **Logfire** - Observability and tracing
* **Pre-commit hooks** - Code quality (Black, Ruff, MyPy)

***

## Data Schema Requirements

### Resume Schema Must Include:

* **Contact Info**: name, email, phone, location (+ optional LinkedIn, portfolio)
* **Education**: degree, institution, graduation\_date (+ optional GPA, coursework)
* **Experience**: company, title, dates, responsibilities, achievements
* **Skills**: name, proficiency\_level (Beginner/Intermediate/Advanced/Expert), optional years
* **Metadata**: trace\_id, generated\_at, prompt\_template, fit\_level, writing\_style

### Job Description Schema Must Include:

* **Company**: name, industry, size, location
* **Requirements**: required\_skills\[], preferred\_skills\[], education, experience\_years, experience\_level
* **Metadata**: trace\_id, generated\_at, is\_niche\_role (boolean flag)

### Validation Rules:

* Email must be valid format
* Phone must be ≥10 characters
* Dates must be ISO format
* GPA must be 0.0-4.0
* Experience years must be 0-30
* end\_date must be after start\_date (if present)

***

## 🧪 Key Implementation Challenges

### Challenge 1: Multi-Template Generation

Don't generate monotonous data. Implement **5+ prompt templates** with distinct characteristics:

* Formal/corporate tone
* Casual/startup-friendly
* Technical/detail-heavy
* Achievement-focused (metrics-driven)
* Career-changer (transferable skills)

**Why it matters**: Real resumes have diverse writing styles. Your failure detection must work across all of them.

### Challenge 2: Controlled Fit Level Generation

Generating a "poor fit" resume is harder than it sounds. You must:

* Intentionally create skill gaps
* Misalign experience levels
* Introduce subtle mismatches (not obvious failures)

**Why it matters**: Your labeling system needs challenging test cases to prove it works.

### Challenge 3: Skill Normalization

"Python", "Python 3.10", "python developer" should all match. Implement normalization:

* Lowercase conversion
* Version number removal
* Suffix stripping (.js, developer, engineer)

**Why it matters**: Without normalization, Jaccard similarity will be artificially low.

### Challenge 4: Hallucination Detection

Rule-based detection is tricky. Consider these patterns:

* Entry-level resume (\<2 years) claiming "expert" in 10+ skills
* Resume listing 30+ skills with most marked "expert"
* Phrases like "expert in all", "certified in everything"
* Inconsistent timelines (overlapping jobs, impossible progressions)

**Why it matters**: LLMs hallucinate. Your system must catch it.

### Challenge 5: Awkward Language Detection

Identify AI-generated or buzzword-heavy text using pattern matching:

* Repeated corporate jargon: "synergy", "thinking outside the box", "move the needle"
* Repetitive patterns: same word 3+ times in close proximity
* Excessive buzzword density: >5 buzzwords in summary/description

**Why it matters**: Distinguishes authentic resumes from low-quality AI-generated ones.

***

## 📦 Deliverables

Your completed system must produce:

### 1. **Generated Data** (JSONL format)

* `resumes_{timestamp}.jsonl` - All generated resumes
* `jobs_{timestamp}.jsonl` - All generated job descriptions
* `pairs_{timestamp}.jsonl` - Resume-job pairs with metadata

### 2. **Validation Results** (JSON/CSV format)

* `validated_data_{timestamp}.json` - Successfully validated records
* `invalid_{timestamp}.jsonl` - Failed records with error details
* `schema_failure_modes_{timestamp}.json` - Error analysis

### 3. **Failure Analysis** (JSONL format)

* `failure_labels_{timestamp}.jsonl` - All calculated metrics per pair
* Statistics: overall failure rates, correlations, distributions

### 4. **Visualizations** (PNG format)

Generate at least these heatmaps/charts:

* **Failure mode correlation matrix** - Which failures co-occur?
* **Failure rates by fit level** - Do "poor fit" resumes fail more?
* **Failure rates by template** - Which writing styles cause issues?
* **Niche vs standard roles** - Do niche jobs have different patterns?
* **Schema validation heatmap** - Which fields fail most often?

### 5. **REST API**

Functional FastAPI service with:

* `POST /review-resume` - Real-time resume analysis
* `GET /health` - Health check
* `GET /analysis/failure-rates` - Aggregate statistics
* Automatic OpenAPI documentation at `/docs`

### 6. **Pipeline Summary** (JSON format)

* `pipeline_summary_{timestamp}.json` - Complete run statistics:
* Total records generated
* Validation success rate
* Failure mode distribution
* Correction success rate (if enabled)
* Processing time per stage

***

## 🎨 Visualization Requirements

All visualizations must use **Matplotlib**, **Seaborn**, or **Plotly**. Save each as a PNG file in a `visualizations/` directory.

### Required Charts

* **Failure Mode Correlation Matrix** (heatmap): Which failure modes co-occur across resume-job pairs?
* **Failure Rates by Fit Level** (grouped bar chart): Do "poor fit" resumes fail more than "excellent fit" ones?
* **Failure Rates by Template** (grouped bar chart): Which writing styles (formal, casual, technical, etc.) cause the most issues?
* **Niche vs Standard Roles** (side-by-side bar chart): Do niche jobs have different failure patterns?
* **Schema Validation Heatmap** (heatmap): Which fields fail validation most often, by error category?
* **Hallucination by Seniority** (stacked bar chart): Do entry-level resumes hallucinate more than senior ones?

### Quality Standards

* All charts must have descriptive titles, axis labels, and legends
* Use appropriate color schemes (diverging for correlations, sequential for rates)
* Include grid lines for readability
* Add annotations for key thresholds and targets

***

## 🔄 Iteration Logs

Every configuration or threshold change must be documented. Use this format:

```
## Iteration Log Entry

| Field | Value |
| --- | --- |
| Date | YYYY-MM-DD |
| Component | (e.g., Generator, Validator, Labeler, Correction Loop, API) |
| Change | What was modified |
| Reason | Why the change was made |
| Before Metric | Value before the change |
| After Metric | Value after the change |
| Delta | Improvement or regression |
| Keep/Revert | Decision and rationale |
```

Example iteration entries:

| Date       | Component       | Change                                                | Before               | After                | Delta | Decision |
| ---------- | --------------- | ----------------------------------------------------- | -------------------- | -------------------- | ----- | -------- |
| 2025-01-15 | Generator       | Added explicit date format instruction to prompt      | Validation: 82%      | Validation: 91%      | +9%   | Keep     |
| 2025-01-16 | Labeler         | Added version stripping to skill normalization        | Jaccard avg: 0.28    | Jaccard avg: 0.41    | +0.13 | Keep     |
| 2025-01-17 | Correction Loop | Included Pydantic error messages in correction prompt | Correction rate: 38% | Correction rate: 62% | +24%  | Keep     |
| 2025-01-18 | Hallucination   | Lowered expert skill threshold from 15 to 10          | Detection: 45%       | Detection: 72%       | +27%  | Keep     |

***

## 🔄 Correction Loop Strategy

When validation fails, your system should:

* **Extract Error Context**: Field path, error type, invalid value, expected format
* **Construct Correction Prompt**: `The following data failed validation with these errors: [error details] Original data: [invalid data] Please generate a corrected version that fixes these issues.`
* **Re-validate**: Parse corrected output and validate again
* **Retry Logic**: Up to 3 attempts, then mark as permanently failed
* **Track Statistics**: Success rate, average attempts, common failure reasons

**Success Criteria**: >50% of invalid records successfully corrected within 3 attempts.

***

## 🧠 LLM-as-Judge (Advanced Feature)

For subtle quality issues that rule-based systems miss, implement an LLM judge that evaluates:

### Evaluation Criteria:

* **Hallucinations**: Unverifiable claims, timeline inconsistencies
* **Awkward Language**: Excessive jargon, unnatural phrasing, AI patterns
* **Fit Assessment**: Holistic skills/experience alignment
* **Red Flags**: Employment gaps, inconsistent career progression

### Output Schema:

```
{
  "has_hallucinations": boolean,
  "hallucination_details": "string (explanation)",
  "has_awkward_language": boolean,
  "awkward_language_details": "string (explanation)",
  "overall_quality_score": 0.0-1.0,
  "fit_assessment": "narrative assessment",
  "recommendations": ["actionable suggestions"],
  "red_flags": ["concerns identified"]
}
```

**Trade-off**: LLM judge is slower (\~5-10s per pair) but catches nuanced issues. Make it optional.

***

## 🎯 Evaluation Approach

Follow these steps in order. Record every result in your iteration log.

### Step 1: Validate Data Generation Volume and Diversity

Generate at least 50 job descriptions across diverse industries. For each job, generate 5-10 resumes with controlled fit levels. Verify coverage of all 5 fit levels and all 5 prompt templates.

Example output:

| Fit Level        | Count | % of Total | Avg Skill Overlap |
| ---------------- | ----- | ---------- | ----------------- |
| Excellent (80%+) | 55    | 22%        | 0.87              |
| Good (60-80%)    | 52    | 21%        | 0.71              |
| Partial (40-60%) | 50    | 20%        | 0.49              |
| Poor (20-40%)    | 48    | 19%        | 0.31              |
| Mismatch (\<20%) | 45    | 18%        | 0.12              |

**If any fit level has \< 15% of total pairs**, adjust the generation distribution weights. **If total pairs \< 250**, increase the number of jobs or resumes per job.

### Step 2: Check Schema Validation Rate

Run all generated records through Pydantic validation. Target > 90% pass rate. Categorize failures by error type.

Example output:

| Error Category          | Count | % of Failures | Most Common Field         |
| ----------------------- | ----- | ------------- | ------------------------- |
| Missing required fields | 12    | 40%           | experience.achievements   |
| Type mismatches         | 8     | 27%           | skills.proficiency\_level |
| Format violations       | 6     | 20%           | contact.email             |
| Logical inconsistencies | 4     | 13%           | experience.end\_date      |

**If validation rate \< 90%**, inspect the top error category and add explicit formatting instructions to the generation prompt for that field. **If a single field accounts for > 50% of failures**, add a Pydantic field validator with a clear error message.

### Step 3: Verify Failure Labeling Accuracy

Manually spot-check 10 resume-job pairs. Verify Jaccard similarity, experience mismatch, seniority mismatch, missing core skills, hallucination, and awkward language flags are calculated correctly.

Example output:

| Pair ID   | Jaccard | Exp Mismatch | Seniority Mismatch | Missing Core | Hallucination | Awkward Lang | Manual Agrees? |
| --------- | ------- | ------------ | ------------------ | ------------ | ------------- | ------------ | -------------- |
| pair\_001 | 0.33    | Yes          | No                 | Yes          | No            | No           | Yes            |
| pair\_002 | 0.85    | No           | No                 | No           | No            | No           | Yes            |
| pair\_003 | 0.12    | Yes          | Yes                | Yes          | No            | Yes          | Yes            |

**If manual agreement \< 80%**, review the normalization logic for skills matching. **If hallucination detection misses obvious cases**, add more pattern rules (e.g., entry-level with 10+ expert skills).

### Step 4: Test Correction Loop Effectiveness

Run the correction loop on all invalid records. Target > 50% correction success within 3 attempts.

Example output:

| Attempt   | Records In | Corrected | Still Invalid | Success Rate |
| --------- | ---------- | --------- | ------------- | ------------ |
| 1         | 30         | 18        | 12            | 60%          |
| 2         | 12         | 5         | 7             | 42%          |
| 3         | 7          | 2         | 5             | 29%          |
| **Total** | **30**     | **25**    | **5**         | **83%**      |

**If overall correction rate \< 50%**, improve the correction prompt by including the specific Pydantic error messages and the expected format. **If most failures persist across all 3 attempts**, check whether the error type is something the LLM can reasonably fix (e.g., logical date ordering vs. missing domain knowledge).

### Step 5: Validate API Performance

Test each endpoint with representative payloads. Measure response times and verify error handling for edge cases.

Example output:

| Endpoint                    | Payload                | Response Time | Status | Edge Case Handled? |
| --------------------------- | ---------------------- | ------------- | ------ | ------------------ |
| POST /review-resume         | Full pair (no judge)   | 1.2s          | 200    | N/A                |
| POST /review-resume         | Full pair (with judge) | 7.8s          | 200    | N/A                |
| POST /review-resume         | Empty skills list      | 0.8s          | 200    | Yes                |
| POST /review-resume         | Missing fields         | 0.3s          | 422    | Yes                |
| GET /health                 | N/A                    | 0.1s          | 200    | N/A                |
| GET /analysis/failure-rates | N/A                    | 0.5s          | 200    | N/A                |

**If response time > 2s without judge**, profile the analysis pipeline and cache repeated computations. **If edge cases return 500 errors**, add input validation middleware with informative error messages.

### Step 6: Self-Evaluation Questions

After completing steps 1-5, answer these questions honestly:

* Can you explain why a "poor fit" resume was labeled as such?
* Do your visualizations reveal non-obvious patterns (e.g., template bias, niche role challenges)?
* Does the correction loop actually improve data quality, or does it just mask errors?
* Can the API handle edge cases (empty skills, missing fields, malformed JSON)?
* Are failure modes distributed as expected across fit levels?

***

## 💡 First Principles

**Why generate synthetic resume-job pairs instead of using real data?** Real resume data is sensitive and expensive to collect. Synthetic generation lets you produce hundreds of diverse examples at low cost while controlling for specific quality dimensions (fit level, writing style, skill distribution). The tradeoff is that synthetic data can drift from reality, which is why validation and failure detection are essential.

**Why use Pydantic for validation instead of manual checks?** Manual validation is error-prone and hard to maintain. Pydantic enforces structural rules at the schema level, catches type mismatches automatically, and produces detailed error messages that can be fed back into the correction loop. It turns validation from a manual review step into an automated, repeatable process.

**Why measure 6 failure modes separately instead of a single quality score?** A single score hides the structure of the problem. If 80% of your failures come from hallucinated skills, that requires a different fix than if failures are spread evenly across all modes. Separate metrics let you target corrections precisely and measure whether each fix actually worked.

**Why include a correction loop?** Generation is imperfect. Rather than discarding every invalid record, feeding validation errors back to the LLM gives it a chance to fix specific issues. This mirrors real-world data pipelines where automated repair is cheaper than regeneration. Tracking correction success rates tells you whether the loop is actually helping or just masking problems.

**Why expose the system as an API?** A pipeline that only runs as a batch script is useful for analysis but not for real-time applications. Wrapping the analysis logic in a REST API makes it usable by other systems (e.g., an HR tool that checks resumes on submission). It also forces you to handle edge cases, error responses, and performance constraints that batch processing can ignore.

***

## 💡 Bonus Challenges (Optional)

If you want to go beyond the baseline:

### 1. **Multi-Hop Questions for Evaluation**

Generate test questions that require understanding multiple resume sections:

* "Does this candidate's education and experience align with the job's seniority level?"
* "Are the claimed skills consistent with the job titles and responsibilities?"

### 2. **Feedback Classification**

Add thumbs up/down feedback mechanism to API responses, log to Braintrust for continuous improvement.

### 3. **Advanced RAG Integration**

Store resumes in a vector database, implement semantic search for "find similar candidates".

### 4. **Prompt Template Optimization**

A/B test different prompt templates, measure which produces highest validation rates.

### 5. **Synthetic Data Augmentation**

Generate "corrected" versions of failed resumes, compare failure rates before/after.

***

## 🚀 Getting Started Hints

### Recommended Development Order:

* **Start with schemas** - Define Pydantic models with all validation rules
* **Build generators** - Get LLM generation working with one template first
* **Implement validation** - Ensure you can catch and categorize errors
* **Add failure labeling** - Start with Jaccard similarity, then add other metrics
* **Create visualizations** - Prove your labeling system works
* **Build API** - Expose functionality for real-time use
* **Add correction loop** - Improve data quality iteratively
* **Integrate observability** - Add Braintrust/Logfire if desired

### Common Pitfalls to Avoid:

* **Don't hardcode prompts** - Use templates with variable injection
* **Don't skip normalization** - Skill matching will fail without it
* **Don't ignore edge cases** - Handle missing fields, empty lists, null values
* **Don't generate all data at once** - Use batch processing with progress tracking
* **Don't forget trace IDs** - Essential for debugging and linking records

### Storage Strategy:

* Use **JSONL** for generated data (streaming-friendly, line-by-line processing)
* Use **JSON** for summaries and analysis results
* Use **CSV** for tabular exports (easy to load in pandas/Excel)
* Use **PNG** for visualizations (widely compatible)

***

## 📚 Key Concepts to Understand

### Jaccard Similarity

```
Given two sets A and B:
Jaccard(A, B) = |A ∩ B| / |A ∪ B|

Example:
Resume skills: {python, javascript, react, node}
Job requirements: {python, javascript, docker, kubernetes}

Intersection: {python, javascript} = 2 items
Union: {python, javascript, react, node, docker, kubernetes} = 6 items
Jaccard = 2/6 = 0.33 (poor overlap)
```

### Seniority Level Mapping

```
Entry/Junior: 0
Mid/Intermediate: 1
Senior: 2
Lead/Principal/Staff: 3
Executive/Director/VP: 4

Mismatch if |resume_level - job_level| > 1
```

### Experience Calculation

```
For each job:
  if end_date exists:
    duration = end_date - start_date
  else:
    duration = today - start_date  # Current job

total_experience = sum(all durations)
```

***

## ✅ Final Success Criteria

Before submitting, verify that your implementation meets all of the following:

### Data Generation

* \[ ] 50+ job descriptions generated across diverse industries
* \[ ] 5-10 resumes per job with controlled fit levels (250+ total pairs)
* \[ ] All 5 fit levels represented (excellent, good, partial, poor, mismatch)
* \[ ] All 5 prompt templates used (formal, casual, technical, achievement, career-changer)
* \[ ] Niche role detection flag set correctly
* \[ ] All records have trace IDs and timestamps

### Schema Validation

* \[ ] Pydantic models defined for Resume, JobDescription, and ResumePair
* \[ ] Validation rules enforced (email format, date ordering, GPA range, etc.)
* \[ ] Validation success rate > 90%
* \[ ] Error categorization by type (missing fields, type mismatches, format violations, logical inconsistencies)
* \[ ] Valid and invalid records saved separately with proper filenames

### Failure Labeling

* \[ ] All 6 failure metrics calculated for every pair (skills overlap, experience mismatch, seniority mismatch, missing core skills, hallucination, awkward language)
* \[ ] Skill normalization implemented (lowercase, version removal, suffix stripping)
* \[ ] Jaccard similarity correctly calculated and spot-checked on 10+ pairs
* \[ ] Hallucination detection covers entry-level overclaiming, excessive expert ratings, impossible timelines
* \[ ] Awkward language detection catches buzzword density and repetitive patterns

### Correction Loop

* \[ ] Correction prompt includes specific Pydantic error messages
* \[ ] Maximum 3 retry attempts per record
* \[ ] Correction success rate > 50%
* \[ ] Statistics tracked (attempts per success, failure reasons)

### LLM-as-Judge

* \[ ] Evaluates hallucinations, awkward language, fit assessment, red flags
* \[ ] Structured output with scores and explanations
* \[ ] Optional (can be enabled/disabled per request)

### API

* \[ ] POST /review-resume responds in \< 2s (without judge), \< 10s (with judge)
* \[ ] GET /health returns health status
* \[ ] GET /analysis/failure-rates returns aggregate statistics
* \[ ] All endpoints return valid JSON with proper error handling
* \[ ] Edge cases handled (empty skills, missing fields, malformed input)

### Visualizations

* \[ ] Failure mode correlation matrix (heatmap)
* \[ ] Failure rates by fit level (grouped bar chart)
* \[ ] Failure rates by template (grouped bar chart)
* \[ ] Niche vs standard roles (side-by-side bar chart)
* \[ ] Schema validation heatmap
* \[ ] Hallucination by seniority (stacked bar chart)
* \[ ] All charts saved as PNG with Matplotlib, Seaborn, or Plotly

### Iteration Logs and Traceability

* \[ ] Every threshold or weight change documented with reason, before/after metrics, and delta
* \[ ] At least 3 iteration log entries showing experimentation
* \[ ] Final configuration decisions traceable to specific iteration log entries

### Testing and Documentation

* \[ ] Pipeline runs end-to-end without crashes
* \[ ] Output files saved with timestamps (resumes, jobs, pairs, labels, summaries)
* \[ ] Pipeline summary JSON includes total records, validation rate, failure distribution, correction rate, timing
* \[ ] You can explain why any given resume was labeled with specific failure modes

**Remember**: This isn't about following a step-by-step tutorial. It's about understanding the problem, making architectural decisions, and proving your solution works through rigorous evaluation. Good luck!

​
