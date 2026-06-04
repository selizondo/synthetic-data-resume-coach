"""Resume and job description generators (jobs-first pipeline flow)."""

import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import logfire
from openai import RateLimitError
from llm_utils import instructor_complete

from .prompts import load_resume_prompt_templates, load_prompt
from .schema import (
    FitLevel,
    SeniorityLevel,
    JobDescription,
    JobDescriptionMetadata,
    Resume,
    ResumeJobPair,
    ResumeJobPairMetadata,
    ResumeMetadata,
)
from .utils.storage import get_timestamped_filename, save_jsonl
from .utils.trace import generate_trace_id


# ── Shared constants ───────────────────────────────────────────────────────────

INDUSTRIES = [
    "Technology",
    "Healthcare",
    "Finance",
    "Education",
    "Marketing",
    "Engineering",
    "Data Science",
    "Design",
    "Sales",
    "Operations",
    "E-commerce",
    "Manufacturing",
    "Consulting",
    "Media",
]

REMOTE_POLICIES = ["Remote", "Hybrid", "On-site"]

EXPERIENCE_LEVELS = [
    "Entry-level (0-2 years)",
    "Mid-level (3-5 years)",
    "Senior (6-10 years)",
    "Lead/Principal (10+ years)",
]

def _years_to_exp_level(years: int) -> str:
    """Human-readable label for resume metadata display."""
    level = SeniorityLevel.from_years(years)
    labels = {
        SeniorityLevel.ENTRY:     EXPERIENCE_LEVELS[0],
        SeniorityLevel.MID:       EXPERIENCE_LEVELS[1],
        SeniorityLevel.SENIOR:    EXPERIENCE_LEVELS[2],
        SeniorityLevel.LEAD:      EXPERIENCE_LEVELS[3],
        SeniorityLevel.EXECUTIVE: EXPERIENCE_LEVELS[3],
    }
    return labels[level]


NICHE_ROLES = {
    "blockchain", "quantum computing", "ai ethics", "robotics",
    "bioinformatics", "cryptography", "embedded systems", "fpga",
    "compiler", "kernel", "hpc", "mlops", "devsecops", "sre", "reliability",
}

def _detect_resume_seniority(resume) -> SeniorityLevel:
    """Infer candidate seniority from resume — mirrors FailureLabeler logic."""
    from datetime import date
    if resume.experience:
        level = SeniorityLevel.from_title(resume.experience[0].title)
        if level == SeniorityLevel.MID:
            total_years = sum(
                ((exp.end_date or date.today()) - exp.start_date).days / 365
                for exp in resume.experience
            )
            level = SeniorityLevel.from_years(total_years)
        return level
    return SeniorityLevel.MID


def _seniority_check_passes(candidate: SeniorityLevel, job: SeniorityLevel, fit_level: FitLevel) -> bool:
    """Return True if the generated candidate's seniority satisfies the fit level constraint."""
    gap = candidate - job
    if fit_level in (FitLevel.EXCELLENT, FitLevel.GOOD):
        return abs(gap) <= 1
    elif fit_level == FitLevel.PARTIAL:
        return gap <= 1
    elif fit_level == FitLevel.POOR:
        return gap <= 0
    else:  # MISMATCH
        return abs(gap) > 1


# Spec-defined overlap targets per fit level (lo inclusive, hi exclusive)
FIT_OVERLAP_RANGE: dict[FitLevel, tuple[float, float]] = {
    FitLevel.EXCELLENT: (0.80, 1.01),
    FitLevel.GOOD:      (0.60, 0.80),
    FitLevel.PARTIAL:   (0.40, 0.60),
    FitLevel.POOR:      (0.20, 0.40),
    FitLevel.MISMATCH:  (0.00, 0.20),
}


def _normalize_skill(skill: str) -> str:
    import re
    n = skill.lower().strip()
    n = re.sub(r"\s*\d+(\.\d+)*\s*", "", n)
    for suffix in [".js", ".py", " developer", " engineer", " programming"]:
        n = n.replace(suffix, "")
    return n.strip()


def _compute_overlap(resume, required_skills: list[str]) -> float:
    """Jaccard similarity between resume skills and job required skills."""
    resume_set = {_normalize_skill(s.name) for s in resume.skills}
    job_set    = {_normalize_skill(s) for s in required_skills}
    if not resume_set or not job_set:
        return 0.0
    return len(resume_set & job_set) / len(resume_set | job_set)


def _overlap_in_range(overlap: float, fit_level: FitLevel) -> bool:
    lo, hi = FIT_OVERLAP_RANGE[fit_level]
    return lo <= overlap < hi


FIT_INSTRUCTIONS: dict[FitLevel, str] = {
    FitLevel.EXCELLENT: "Include ALL required skills with Expert proficiency.",
    FitLevel.GOOD:      "Include 80% of required skills with Advanced proficiency.",
    FitLevel.PARTIAL:   "Include about 50% of required skills with varying proficiency.",
    FitLevel.POOR:      "Include only 20-30% of required skills, mostly at Beginner level.",
    FitLevel.MISMATCH:  "Include skills from a completely different field. Do NOT include any of the required skills listed above.",
}

TEMPLATE_STYLE_HINTS: dict[str, str] = {
    "formal":              "Write in a formal, traditional resume style.",
    "casual":              "Write in a friendly, approachable tone.",
    "technical":           "Use precise, technical language. Quantify achievements with metrics. Do not add skills beyond those required by the job.",
    "achievement_focused": "Lead every bullet with a quantified achievement (numbers, percentages, scale).",
    "career_changer":      "Frame the candidate as transitioning from a different field. Emphasize transferable skills, self-learning, and bootcamps over direct experience.",
}

def _seniority_instruction(fit_level: FitLevel, job_seniority: SeniorityLevel) -> str:
    if fit_level in (FitLevel.EXCELLENT, FitLevel.GOOD):
        return f"The candidate's seniority MUST be {job_seniority.label} level."
    elif fit_level == FitLevel.PARTIAL:
        target = job_seniority.below(1)
        return f"The candidate's seniority must be {target.label} (one level below the {job_seniority.label} job requirement)."
    elif fit_level == FitLevel.POOR:
        target = job_seniority.below(2)
        return f"The candidate's seniority must be {target.label} (significantly below the {job_seniority.label} job requirement)."
    else:  # MISMATCH
        target = job_seniority.opposite()
        return f"The candidate's seniority MUST be {target.label}, NOT {job_seniority.label}."


def _is_niche_role(title: str) -> bool:
    title_lower = title.lower()
    return any(niche in title_lower for niche in NICHE_ROLES)


# ── ResumeGenerator ────────────────────────────────────────────────────────────

class ResumeGenerator:
    """Generate synthetic resumes using LLM with structured output."""

    _prompt_templates_cache: dict[str, dict] | None = None
    _resume_for_job_tmpl: dict | None = None

    @classmethod
    def _templates(cls) -> dict[str, dict]:
        if cls._prompt_templates_cache is None:
            cls._prompt_templates_cache = load_resume_prompt_templates()
        return cls._prompt_templates_cache

    @classmethod
    def _job_prompt(cls) -> dict:
        if cls._resume_for_job_tmpl is None:
            cls._resume_for_job_tmpl = load_prompt("resume_for_job")
        return cls._resume_for_job_tmpl

    def __init__(self, model: str = "llama-3.3-70b-versatile"):
        self.model = model
        logfire.info("ResumeGenerator initialized", model=model)

    def generate_single(
        self,
        industry: Optional[str] = None,
        experience_level: Optional[str] = None,
        specific_role: Optional[str] = None,
        prompt_template: Optional[str] = None,
        target_job_trace_id: Optional[str] = None,
        fit_level: Optional[FitLevel] = None,
    ) -> Resume:
        """Generate a single synthetic resume from a named prompt template."""
        industry = industry or random.choice(INDUSTRIES)
        experience_level = experience_level or random.choice(EXPERIENCE_LEVELS)
        templates = self._templates()
        prompt_template = prompt_template or random.choice(list(templates.keys()))

        tmpl = templates.get(prompt_template, templates["formal"])
        role_context = f" specifically for a {specific_role} role" if specific_role else ""

        trace_id = generate_trace_id("resume")
        with logfire.span("generate_resume", trace_id=trace_id):
            resume = instructor_complete(
                messages=[
                    {"role": "system", "content": tmpl["system"]},
                    {"role": "user", "content": tmpl["user"].format(
                        industry=industry,
                        experience_level=experience_level,
                        role_context=role_context,
                    )},
                ],
                response_model=Resume,
                model=self.model,
            )
            resume.metadata = ResumeMetadata(
                trace_id=trace_id,
                generated_at=datetime.now(timezone.utc),
                prompt_template=prompt_template,
                target_industry=industry,
                target_seniority=experience_level,
                fit_level=fit_level,
                target_job_trace_id=target_job_trace_id,
            )
            logfire.info("Resume generated", trace_id=trace_id, industry=industry,
                         experience_level=experience_level, prompt_template=prompt_template)
        return resume

    def generate_for_job(
        self,
        job_trace_id: str,
        job_title: str,
        required_skills: list[str],
        industry: str,
        experience_years: int,
        fit_level: FitLevel = FitLevel.GOOD,
        template: Optional[str] = None,
    ) -> Resume:
        """Generate a resume tailored to a specific job with a controlled fit level."""
        exp_level = _years_to_exp_level(experience_years)
        job_seniority = SeniorityLevel.from_years(experience_years)
        fit_match = (
            "matches well with" if fit_level in (FitLevel.EXCELLENT, FitLevel.GOOD)
            else "partially matches" if fit_level == FitLevel.PARTIAL
            else "does not match"
        )
        prompt_template = template or random.choice(list(self._templates().keys()))
        style_hint = TEMPLATE_STYLE_HINTS.get(prompt_template, "")
        trace_id = generate_trace_id("resume")

        fit_instruction = FIT_INSTRUCTIONS.get(fit_level, FIT_INSTRUCTIONS[FitLevel.GOOD])
        if required_skills:
            n = len(required_skills)
            if fit_level == FitLevel.GOOD:
                # Exclude 1 skill so overlap lands in 0.60–0.80
                excluded = required_skills[n - 1:]
                if excluded:
                    fit_instruction += (
                        f" Do NOT include: {', '.join(excluded)}."
                        " Target skill overlap: 60–80%."
                    )
            elif fit_level == FitLevel.PARTIAL:
                # Exclude last 2 skills so overlap lands in 0.40–0.60
                excluded = required_skills[max(1, n - 2):]
                if excluded:
                    fit_instruction += (
                        f" Do NOT include these skills: {', '.join(excluded)}."
                        " Target skill overlap: 40–60%."
                    )
            elif fit_level == FitLevel.POOR:
                # Keep at most 2 skills, exclude the rest
                excluded = required_skills[min(2, n):]
                if excluded:
                    fit_instruction += (
                        f" Do NOT include these skills: {', '.join(excluded)}."
                        " Replace them with unrelated or beginner-level skills."
                        " Target skill overlap: 20–40%."
                    )
            elif fit_level == FitLevel.MISMATCH:
                excluded = required_skills[:min(5, n)]
                fit_instruction += (
                    f" Specifically exclude: {', '.join(excluded)}. "
                    "Target Jaccard skill overlap with the job: < 0.20."
                )

        seniority_line = _seniority_instruction(fit_level, job_seniority)

        tmpl = self._job_prompt()
        style_hint_block = f"WRITING STYLE: {style_hint}\n\n" if style_hint else ""
        system_msg = {
            "role": "system",
            "content": tmpl["system"].format(seniority_line=seniority_line),
        }
        user_prompt = tmpl["user"].format(
            job_title=job_title,
            industry=industry,
            seniority_line=seniority_line,
            required_skills=", ".join(required_skills),
            fit_instruction=fit_instruction,
            style_hint_block=style_hint_block,
            fit_match=fit_match,
        )
        base_messages = [system_msg, {"role": "user", "content": user_prompt}]

        resume = None
        total_attempts = 0
        lo, hi = FIT_OVERLAP_RANGE[fit_level]

        with logfire.span(
            "generate_resume_for_job",
            trace_id=trace_id,
            job_trace_id=job_trace_id,
            fit_level=fit_level.value,
            template=prompt_template,
            industry=industry,
            model=self.model,
            phase="generation",
        ):
            for attempt in range(2):  # max 2 attempts for all fit levels
                messages = base_messages
                if attempt > 0:
                    issues = []
                    if not _seniority_check_passes(candidate_seniority, job_seniority, fit_level):
                        issues.append(
                            f"seniority wrong (was {candidate_seniority.label}, need {seniority_line})"
                        )
                    if not _overlap_in_range(candidate_overlap, fit_level):
                        issues.append(
                            f"skill overlap wrong (was {candidate_overlap:.0%}, "
                            f"target {lo:.0%}–{hi:.0%} for {fit_level.value} fit)"
                        )
                    correction = (
                        f"Previous resume failed: {'; '.join(issues)}. "
                        f"Regenerate fixing ALL issues above."
                    )
                    messages = base_messages + [{"role": "user", "content": correction}]

                candidate = instructor_complete(
                    messages=messages,
                    response_model=Resume,
                    model=self.model,
                )
                candidate_seniority = _detect_resume_seniority(candidate)
                candidate_overlap   = _compute_overlap(candidate, required_skills)

                seniority_ok = _seniority_check_passes(candidate_seniority, job_seniority, fit_level)
                overlap_ok   = _overlap_in_range(candidate_overlap, fit_level)

                if seniority_ok and overlap_ok:
                    resume = candidate
                    total_attempts = attempt + 1
                    break

                logfire.info("Quality check failed, retrying",
                             attempt=attempt + 1, fit_level=fit_level.value,
                             candidate_seniority=candidate_seniority.label,
                             job_seniority=job_seniority.label,
                             candidate_overlap=round(candidate_overlap, 3),
                             overlap_target=f"{lo:.0%}-{hi:.0%}",
                             seniority_ok=seniority_ok,
                             overlap_ok=overlap_ok)
            else:
                resume = candidate  # max attempts reached — use last candidate
                total_attempts = 2

            resume.metadata = ResumeMetadata(
                trace_id=trace_id,
                generated_at=datetime.now(timezone.utc),
                prompt_template=prompt_template,
                target_industry=industry,
                target_seniority=exp_level,
                fit_level=fit_level,
                target_job_trace_id=job_trace_id,
            )
            logfire.info("Resume generated for job", trace_id=trace_id,
                         job_trace_id=job_trace_id, fit_level=fit_level.value,
                         template=prompt_template, industry=industry, model=self.model,
                         total_attempts=total_attempts,
                         final_overlap=round(candidate_overlap, 3),
                         final_seniority=candidate_seniority.label)
        return resume

    def generate_batch(
        self,
        count: int = 10,
        industries: Optional[list[str]] = None,
        experience_levels: Optional[list[str]] = None,
    ) -> list[Resume]:
        """Generate standalone resumes (not tied to a specific job)."""
        industries = industries or INDUSTRIES
        experience_levels = experience_levels or EXPERIENCE_LEVELS
        template_names = list(self._templates().keys())

        resumes = []
        with logfire.span("generate_resume_batch", count=count):
            for i in range(count):
                try:
                    resume = self.generate_single(
                        industry=random.choice(industries),
                        experience_level=random.choice(experience_levels),
                        prompt_template=random.choice(template_names),
                    )
                    resumes.append(resume)
                    logfire.info(f"Generated resume {i + 1}/{count}")
                except Exception as e:
                    logfire.error(f"Failed to generate resume {i + 1}", error=str(e))
        return resumes

    def save_resumes(
        self,
        resumes: list[Resume],
        output_dir: str = "data/generated",
        filename: Optional[str] = None,
    ) -> Path:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        file_path = output_path / (filename or get_timestamped_filename("resumes", "jsonl"))
        save_jsonl(resumes, file_path)
        logfire.info(f"Saved {len(resumes)} resumes to {file_path}")
        return file_path


# ── JobDescriptionGenerator ────────────────────────────────────────────────────

class JobDescriptionGenerator:
    """Generate synthetic job descriptions using LLM with structured output."""

    _job_tmpl: dict | None = None

    @classmethod
    def _prompt(cls) -> dict:
        if cls._job_tmpl is None:
            cls._job_tmpl = load_prompt("job_description")
        return cls._job_tmpl

    def __init__(self, model: str = "llama-3.3-70b-versatile"):
        self.model = model
        logfire.info("JobDescriptionGenerator initialized", model=model)

    def generate_single(
        self,
        title: Optional[str] = None,
        industry: Optional[str] = None,
        seniority_level: Optional[str] = None,
        remote_policy: Optional[str] = None,
        prompt_template: Optional[str] = None,
    ) -> JobDescription:
        """Generate a single synthetic job description."""
        seniority_level = seniority_level or random.choice([s.label for s in SeniorityLevel])
        remote_policy = remote_policy or random.choice(REMOTE_POLICIES)
        industry = industry or random.choice(INDUSTRIES)

        title_context = f"for a {title} position" if title else "for a relevant position"
        trace_id = generate_trace_id("job")

        min_years = SeniorityLevel.from_title(seniority_level).min_years
        tmpl = self._prompt()
        user_prompt = tmpl["user"].format(
            title_context=title_context,
            industry=industry,
            seniority_level=seniority_level,
            remote_policy=remote_policy,
            min_years=min_years,
        )

        with logfire.span("generate_job_description", trace_id=trace_id,
                          industry=industry, seniority=seniority_level,
                          model=self.model, phase="generation"):
            job = instructor_complete(
                messages=[
                    {"role": "system", "content": tmpl["system"]},
                    {"role": "user", "content": user_prompt},
                ],
                response_model=JobDescription,
                model=self.model,
            )
            job.metadata = JobDescriptionMetadata(
                trace_id=trace_id,
                generated_at=datetime.now(timezone.utc),
                prompt_template=prompt_template or "default",
                is_niche_role=_is_niche_role(job.title),
            )
            logfire.info("Job description generated", trace_id=trace_id, title=job.title,
                         company=job.company.name, seniority=seniority_level,
                         is_niche=job.metadata.is_niche_role)
        return job

    def generate_batch(
        self,
        count: int = 10,
        seniority_levels: Optional[list[str]] = None,
        industries: Optional[list[str]] = None,
    ) -> list[JobDescription]:
        """Generate a batch of job descriptions, stratified by seniority and industry."""
        seniority_levels = seniority_levels or [s.label for s in SeniorityLevel]
        industries = industries or INDUSTRIES

        jobs = []
        with logfire.span("generate_job_batch", count=count):
            for i in range(count):
                try:
                    job = self.generate_single(
                        seniority_level=random.choice(seniority_levels),
                        industry=random.choice(industries),
                    )
                    jobs.append(job)
                    logfire.info(f"Generated job {i + 1}/{count}")
                except Exception as e:
                    logfire.error(f"Failed to generate job {i + 1}", error=str(e))
        return jobs

    def generate_with_multiple_resumes(
        self,
        job: JobDescription,
        resume_generator: ResumeGenerator,
        resumes_per_job: int = 5,
        fit_levels: Optional[list[FitLevel]] = None,
    ) -> list[ResumeJobPair]:
        """Generate resumes at each fit level for a single job (jobs-first flow)."""
        fit_levels = fit_levels or list(FitLevel)
        job_trace_id = job.metadata.trace_id if job.metadata else generate_trace_id("job")
        template_names = list(resume_generator._templates().keys())
        pairs = []
        dropped: list[str] = []

        for i in range(resumes_per_job):
            fit_level = fit_levels[i % len(fit_levels)]
            template = random.choice(template_names)
            try:
                resume = resume_generator.generate_for_job(
                    job_trace_id=job_trace_id,
                    job_title=job.title,
                    required_skills=job.requirements.required_skills,
                    industry=job.company.industry,
                    experience_years=job.requirements.experience_years,
                    fit_level=fit_level,
                    template=template,
                )
                pair = ResumeJobPair(
                    resume=resume,
                    job_description=job,
                    metadata=ResumeJobPairMetadata(
                        trace_id=generate_trace_id("pair"),
                        generated_at=datetime.now(timezone.utc),
                        fit_level=fit_level.value,
                    ),
                )
                pairs.append(pair)
                logfire.info(f"Generated resume {i + 1}/{resumes_per_job} for job",
                             job_trace_id=job_trace_id, fit_level=fit_level.value,
                             template=template)
            except Exception as e:
                if isinstance(e, RateLimitError) or "429" in str(e):
                    raise
                dropped.append(fit_level.value)
                logfire.error(f"Failed to generate resume {i + 1} for job",
                              error=str(e), job_trace_id=job_trace_id,
                              fit_level=fit_level.value)

        if dropped:
            logfire.error("pairs_dropped",
                          job_trace_id=job_trace_id,
                          dropped_count=len(dropped),
                          dropped_fit_levels=dropped)

        return pairs

    def save_jobs(
        self,
        jobs: list[JobDescription],
        output_dir: str = "data/generated",
        filename: Optional[str] = None,
    ) -> Path:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        file_path = output_path / (filename or get_timestamped_filename("jobs", "jsonl"))
        save_jsonl(jobs, file_path)
        logfire.info(f"Saved {len(jobs)} job descriptions to {file_path}")
        return file_path

    def save_pairs(
        self,
        pairs: list[ResumeJobPair],
        output_dir: str = "data/generated",
        filename: Optional[str] = None,
    ) -> Path:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        file_path = output_path / (filename or get_timestamped_filename("pairs", "jsonl"))
        save_jsonl(pairs, file_path)
        logfire.info(f"Saved {len(pairs)} pairs to {file_path}")
        return file_path
