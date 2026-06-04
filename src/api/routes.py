"""API routes for the Resume Coach service."""

import time
from datetime import UTC, date, datetime

import logfire
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field

from ..analysis.failure_labeler import FailureLabeler
from ..analysis.llm_judge import LLMJudge
from ..schema import (
    Company,
    ContactInfo,
    Education,
    Experience,
    JobDescription,
    Requirements,
    Resume,
    Skill,
)
from ..utils.trace import generate_trace_id

router = APIRouter()


# Request/Response Models


class ContactInfoInput(BaseModel):
    """Contact information input."""

    name: str = Field(..., min_length=1)
    email: EmailStr
    phone: str = Field(..., min_length=10)
    location: str
    linkedin: str | None = None
    portfolio: str | None = None


class EducationInput(BaseModel):
    """Education input."""

    degree: str
    institution: str
    graduation_date: str  # ISO date string
    gpa: float | None = None
    relevant_coursework: list[str] | None = None


class ExperienceInput(BaseModel):
    """Experience input."""

    company: str
    title: str
    start_date: str  # ISO date string
    end_date: str | None = None  # ISO date string or null for current
    responsibilities: list[str] = Field(default_factory=list, min_length=1)
    achievements: list[str] = Field(default_factory=list)


class SkillInput(BaseModel):
    """Skill input."""

    name: str
    proficiency_level: str  # Beginner, Intermediate, Advanced, Expert
    years_experience: float | None = None


class ResumeInput(BaseModel):
    """Resume input for API."""

    contact: ContactInfoInput
    summary: str | None = None
    education: list[EducationInput] = Field(default_factory=list, min_length=1)
    experience: list[ExperienceInput] = Field(default_factory=list)
    skills: list[SkillInput] = Field(default_factory=list, min_length=1)
    certifications: list[str] | None = None
    languages: list[str] | None = None


class CompanyInput(BaseModel):
    """Company input."""

    name: str
    industry: str
    size: str  # Startup, Small, Medium, Large, Enterprise
    location: str


class RequirementsInput(BaseModel):
    """Job requirements input."""

    required_skills: list[str] = Field(default_factory=list, min_length=1)
    preferred_skills: list[str] = Field(default_factory=list)
    education_requirements: str
    experience_years: int = Field(ge=1, le=30)
    experience_level: str  # Entry, Mid, Senior, Lead, Executive


class JobDescriptionInput(BaseModel):
    """Job description input for API."""

    title: str
    company: CompanyInput
    description: str = Field(..., min_length=50)
    requirements: RequirementsInput
    responsibilities: list[str] = Field(default_factory=list, min_length=1)
    benefits: list[str] = Field(default_factory=list)
    salary_range: str | None = None
    remote_policy: str = "On-site"
    employment_type: str = "Full-time"


class ReviewResumeRequest(BaseModel):
    """Request body for /review-resume endpoint."""

    resume: ResumeInput
    job_description: JobDescriptionInput
    use_llm_judge: bool = Field(
        default=False,
        description="Whether to use LLM for additional quality assessment (slower but more thorough)",
    )


class SkillAnalysis(BaseModel):
    """Skill analysis result."""

    overlap_ratio: float = Field(
        description="Jaccard similarity between resume and job skills (0-1)"
    )
    matched_skills: list[str]
    missing_skills: list[str]


class FailureFlags(BaseModel):
    """Failure flags detected."""

    experience_mismatch: bool
    seniority_mismatch: bool
    missing_core_skill: bool
    hallucinated_skill: bool
    awkward_language: bool


class LLMAssessment(BaseModel):
    """LLM-based assessment (optional)."""

    has_hallucinations: bool
    hallucination_details: str | None
    has_awkward_language: bool
    awkward_language_details: str | None
    quality_score: float
    red_flags: list[str]


class ReviewResumeResponse(BaseModel):
    """Response for /review-resume endpoint."""

    trace_id: str
    overall_fit: str = Field(description="Overall fit: excellent, good, partial, poor, mismatch")
    fit_score: float = Field(ge=0.0, le=1.0, description="Numeric fit score (0-1)")
    skill_analysis: SkillAnalysis
    failure_flags: FailureFlags
    recommendations: list[str]
    llm_assessment: LLMAssessment | None = None
    strategy_used: str = Field(description="Analysis path: 'rule_based' or 'rule_based+llm_judge'")
    latency_ms: float = Field(description="Wall-clock time for this request in milliseconds")
    analyzed_at: str


# Helper functions


def convert_to_resume(input_data: ResumeInput) -> Resume:
    """Convert API input to Resume model."""
    contact = ContactInfo(
        name=input_data.contact.name,
        email=input_data.contact.email,
        phone=input_data.contact.phone,
        location=input_data.contact.location,
        linkedin=input_data.contact.linkedin,
        portfolio=input_data.contact.portfolio,
    )

    education = []
    for edu in input_data.education:
        education.append(
            Education(
                degree=edu.degree,
                institution=edu.institution,
                graduation_date=date.fromisoformat(edu.graduation_date),
                gpa=edu.gpa,
                relevant_coursework=edu.relevant_coursework or [],
            )
        )

    experience = []
    for exp in input_data.experience:
        experience.append(
            Experience(
                company=exp.company,
                title=exp.title,
                start_date=date.fromisoformat(exp.start_date),
                end_date=date.fromisoformat(exp.end_date) if exp.end_date else None,
                responsibilities=exp.responsibilities,
                achievements=exp.achievements,
            )
        )

    skills = []
    for skill in input_data.skills:
        skills.append(
            Skill(
                name=skill.name,
                proficiency_level=skill.proficiency_level,
                years_experience=skill.years_experience,
            )
        )

    return Resume(
        contact=contact,
        summary=input_data.summary,
        education=education,
        experience=experience,
        skills=skills,
        certifications=input_data.certifications,
        languages=input_data.languages,
    )


def convert_to_job(input_data: JobDescriptionInput) -> JobDescription:
    """Convert API input to JobDescription model."""
    company = Company(
        name=input_data.company.name,
        industry=input_data.company.industry,
        size=input_data.company.size,
        location=input_data.company.location,
    )

    requirements = Requirements(
        required_skills=input_data.requirements.required_skills,
        preferred_skills=input_data.requirements.preferred_skills,
        education_requirements=input_data.requirements.education_requirements,
        experience_years=input_data.requirements.experience_years,
        experience_level=input_data.requirements.experience_level,
    )

    return JobDescription(
        title=input_data.title,
        company=company,
        description=input_data.description,
        requirements=requirements,
        responsibilities=input_data.responsibilities,
        benefits=input_data.benefits,
        salary_range=input_data.salary_range,
        remote_policy=input_data.remote_policy,
        employment_type=input_data.employment_type,
    )


def generate_recommendations(
    labels,
    skill_analysis: SkillAnalysis,
    failure_flags: FailureFlags,
) -> list[str]:
    """Generate recommendations based on analysis."""
    recommendations = []

    if skill_analysis.overlap_ratio < 0.5:
        recommendations.append(
            f"Focus on acquiring these key skills: {', '.join(skill_analysis.missing_skills[:3])}"
        )

    if failure_flags.experience_mismatch:
        recommendations.append(
            "Consider gaining more experience or targeting positions with lower experience requirements"
        )

    if failure_flags.seniority_mismatch:
        recommendations.append(
            "Your seniority level may not match this role. Consider roles at your current level or work on leadership skills"
        )

    if failure_flags.missing_core_skill:
        recommendations.append(
            "You're missing a core skill for this role. Prioritize learning it through courses or projects"
        )

    if failure_flags.hallucinated_skill:
        recommendations.append(
            "Review your resume for potentially exaggerated claims. Ensure all skills can be demonstrated"
        )

    if failure_flags.awkward_language:
        recommendations.append(
            "Consider revising your resume language to be more natural and less buzzword-heavy"
        )

    if not recommendations:
        recommendations.append(
            "Your resume is well-matched for this position. Consider highlighting your most relevant achievements"
        )

    return recommendations


FAILURE_PENALTY_PER_FLAG = 0.1  # not empirically tuned; adjust via A/B on labeler output


def calculate_fit_score(
    skill_overlap: float,
    failure_count: int,
    overall_pass: bool = True,
) -> tuple[float, str]:
    """Calculate overall fit score and label."""
    base_score = skill_overlap
    penalty = failure_count * FAILURE_PENALTY_PER_FLAG

    score = max(0.0, min(1.0, base_score - penalty))

    if score >= 0.8:
        fit_level = "excellent"
    elif score >= 0.6:
        fit_level = "good"
    elif score >= 0.4:
        fit_level = "partial"
    elif score >= 0.2:
        fit_level = "poor"
    else:
        fit_level = "mismatch"

    # Binary labeler gates override soft score when it disagrees.
    if not overall_pass and fit_level in ("excellent", "good"):
        fit_level = "partial"

    return score, fit_level


# Endpoints


@router.post("/review-resume", response_model=ReviewResumeResponse)
async def review_resume(request: ReviewResumeRequest):
    """
    Analyze a resume against a job description.

    Returns structured analysis including:
    - Skills overlap analysis (Jaccard similarity)
    - Failure mode detection
    - Recommendations for improvement
    - Optional LLM-based quality assessment
    """
    trace_id = generate_trace_id("review")
    _start = time.perf_counter()

    with logfire.span("review_resume", trace_id=trace_id):
        try:
            # Convert inputs to internal models
            resume = convert_to_resume(request.resume)
            job = convert_to_job(request.job_description)

            # Run failure labeling
            labeler = FailureLabeler()
            labels = labeler.label_pair(resume, job, trace_id)

            # Build response components
            skill_analysis = SkillAnalysis(
                overlap_ratio=labels.skills_overlap_ratio,
                matched_skills=labels.matched_skills,
                missing_skills=labels.missing_skills,
            )

            failure_flags = FailureFlags(
                experience_mismatch=labels.experience_mismatch == 1,
                seniority_mismatch=labels.seniority_mismatch == 1,
                missing_core_skill=labels.missing_core_skill == 1,
                hallucinated_skill=labels.hallucinated_skill == 1,
                awkward_language=labels.awkward_language_flag == 1,
            )

            # Calculate fit score — overall_pass gates the level to prevent
            # contradictions between the soft score and binary labeler flags.
            fit_score, fit_level = calculate_fit_score(
                labels.skills_overlap_ratio,
                labels.failure_count,
                labels.overall_pass,
            )

            # Generate recommendations
            recommendations = generate_recommendations(
                labels, skill_analysis, failure_flags
            )

            # Optional LLM assessment
            llm_assessment = None
            if request.use_llm_judge:
                try:
                    judge = LLMJudge()
                    judgment = judge.judge_pair(resume, job, trace_id)

                    llm_assessment = LLMAssessment(
                        has_hallucinations=judgment.result.has_hallucinations,
                        hallucination_details=judgment.result.hallucination_details,
                        has_awkward_language=judgment.result.has_awkward_language,
                        awkward_language_details=judgment.result.awkward_language_details,
                        quality_score=judgment.result.overall_quality_score,
                        red_flags=judgment.result.red_flags,
                    )

                    # Add LLM recommendations
                    recommendations.extend(judgment.result.recommendations[:3])
                except Exception as e:
                    logfire.warning(f"LLM judge failed: {e}")

            strategy = "rule_based+llm_judge" if request.use_llm_judge and llm_assessment else "rule_based"
            response = ReviewResumeResponse(
                trace_id=trace_id,
                overall_fit=fit_level,
                fit_score=fit_score,
                skill_analysis=skill_analysis,
                failure_flags=failure_flags,
                recommendations=recommendations[:5],  # Limit to 5
                llm_assessment=llm_assessment,
                strategy_used=strategy,
                latency_ms=round((time.perf_counter() - _start) * 1000, 1),
                analyzed_at=datetime.now(UTC).isoformat(),
            )

            logfire.info(
                "Resume review complete",
                trace_id=trace_id,
                fit_level=fit_level,
                fit_score=fit_score,
                strategy_used=strategy,
                latency_ms=response.latency_ms,
            )

            return response

        except Exception as e:
            logfire.error(f"Review failed: {e}", trace_id=trace_id)
            raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/analysis/failure-rates")
async def get_failure_rates(labeled_dir: str = "data/labeled"):
    """Get aggregate failure rate statistics from the most recent labeled JSONL file."""
    import json
    from pathlib import Path

    # Prevent path traversal: labeled_dir must resolve inside data/
    safe_base = Path("data").resolve()
    labeled_path = Path(labeled_dir).resolve()
    if not str(labeled_path).startswith(str(safe_base)):
        raise HTTPException(status_code=400, detail="Invalid labeled_dir")

    labeled_path = Path(labeled_dir)
    label_files = sorted(
        labeled_path.glob("failure_labels_*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not label_files:
        raise HTTPException(
            status_code=404,
            detail=f"No failure label files found in {labeled_dir}. Run the pipeline first.",
        )

    latest_file = label_files[0]
    records = []
    try:
        with open(latest_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read {latest_file}: {e}") from e

    if not records:
        raise HTTPException(status_code=404, detail="No records found in latest label file.")

    total = len(records)
    avg_overlap = sum(r.get("skills_overlap_ratio", 0.0) for r in records) / total
    failure_fields = [
        "experience_mismatch",
        "seniority_mismatch",
        "missing_core_skill",
        "hallucinated_skill",
        "awkward_language_flag",
    ]
    failure_rates = {
        field: sum(r.get(field, 0) for r in records) / total
        for field in failure_fields
    }
    overall_pass_rate = sum(
        1
        for r in records
        if (
            r.get("skills_overlap_ratio", 0.0) >= 0.5
            and all(r.get(f, 0) == 0 for f in failure_fields)
        )
    ) / total

    return {
        "source_file": str(latest_file),
        "total_analyzed": total,
        "overall_pass_rate": round(overall_pass_rate, 4),
        "average_skills_overlap": round(avg_overlap, 4),
        "failure_rates": {k: round(v, 4) for k, v in failure_rates.items()},
    }


@router.get("/analysis/label-quality")
async def get_label_quality(run_label: str = "", labeled_dir: str = "data/labeled"):
    """Return the label quality report for a specific or the latest pipeline run.

    Reads label_quality_<run_label>.json produced by phase5_eval (--eval-quality).
    If run_label is omitted, returns the most recent report available.
    """
    import json
    from pathlib import Path

    # Prevent path traversal: labeled_dir must resolve inside data/
    safe_base = Path("data").resolve()
    labeled_path = Path(labeled_dir).resolve()
    if not str(labeled_path).startswith(str(safe_base)):
        raise HTTPException(status_code=400, detail="Invalid labeled_dir")

    labeled_path = Path(labeled_dir)

    if run_label:
        report_file = labeled_path / f"label_quality_{run_label}.json"
        if not report_file.exists():
            raise HTTPException(
                status_code=404,
                detail=f"No label quality report for run '{run_label}'. "
                       "Run: python -m src.main --eval-quality --resume <run_label>",
            )
    else:
        candidates = sorted(
            labeled_path.glob("label_quality_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            raise HTTPException(
                status_code=404,
                detail=f"No label quality reports found in {labeled_dir}. "
                       "Run: python -m src.main --eval-quality",
            )
        report_file = candidates[0]

    try:
        return json.loads(report_file.read_text())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read {report_file}: {e}") from e
