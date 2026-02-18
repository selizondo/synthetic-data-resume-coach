# Synthetic Data Resume Coach (P2)

Production-grade synthetic data pipeline that generates, validates, analyzes, and corrects resume-job description pairs using LLMs — acting as an intelligent resume coach that identifies mismatches and provides actionable feedback.

Spec: [synthetic_data_resume_coach.md](synthetic_data_resume_coach.md)

---

## Objective

**Problem:** Hiring managers receive hundreds of resumes per posting. Most are poorly matched: wrong skills, mismatched seniority, or filled with buzzword noise. There is no automated way to generate realistic labeled training data for resume-matching systems at scale.

**Solution:** An end-to-end pipeline that generates resume-job pairs with controlled fit levels, validates them, analyzes failure patterns, optionally corrects invalid data via LLM feedback, and exposes the intelligence through a REST API.

**Core challenge:** Generating diverse, realistic resume-job pairs with controlled quality levels (excellent → complete mismatch) while maintaining >90% schema validity and providing diagnostic analysis of why specific resumes fail.

**Five pipeline phases:**

| Phase | What happens |
|---|---|
| **1. Generate** | Job descriptions (with niche role detection) → resumes at 5 controlled fit levels → resume-job pairs with metadata |
| **2. Validate** | Pydantic schema checks → error extraction and categorization → valid/invalid split |
| **3. Analyze** | Failure metrics (Jaccard, experience gaps) → optional LLM judge for subtle issues → correlation matrices + heatmaps |
| **4. Correct** | Feed validation errors back to LLM → re-validate → track correction success rates |
| **5. API** | FastAPI REST endpoints: POST /review-resume, GET /health, GET /analysis/failure-rates |

**Fit levels generated:** Excellent (80%+ skill overlap), Good (60–80%), Partial (40–60%), Poor (20–40%), Mismatch (<20%).

**Success targets:** 50+ job descriptions, 5–10 resumes per job, >90% validation pass rate, API response <2s.

---

## Setup

```bash
pip install -e .
cp .env.example .env   # set LLM_API_KEY / LLM_BASE_URL
```

---

## Run

```bash
# Generate resume-job pairs
python src/main.py generate --n-jobs 50

# Validate generated data
python src/main.py validate

# Run analysis + charts
python src/main.py analyze

# Correct invalid records
python src/main.py correct

# Start API server
python src/main.py serve
```

---

## Project Layout

```
synthetic_data_resume_coach/
├── src/
│   ├── main.py              # CLI entry point
│   ├── generators.py        # Job description + resume generation (LLM)
│   ├── validators.py        # Pydantic schema validation + error categorization
│   ├── analysis/            # Metrics, charts, LLM judge
│   ├── correction/          # LLM-driven data correction loop
│   ├── api/                 # FastAPI endpoints
│   └── models.py            # JobDescription, Resume, ResumePair schemas
├── data/generated/          # Output pairs (JSONL)
├── tests/
├── synthetic_data_resume_coach.md   # Full project spec
└── blog_Synthetic_Data_Resume_Coach.md
```
