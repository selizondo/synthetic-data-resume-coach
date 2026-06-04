"""All Pydantic data models for the Resume Coach pipeline.

Organized in dependency order:
  1. Enums and shared constants
  2. Resume models (ContactInfo → Education → Experience → Skill → ResumeMetadata → Resume)
  3. Job description models (Company → Requirements → JobDescriptionMetadata → JobDescription)
  4. Pair model (ResumeJobPairMetadata → ResumeJobPair)
  5. Validation types (ValidationError_, ValidationResult, SchemaValidator)
"""

import json
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import date, datetime
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Any

import logfire
from pydantic import BaseModel, EmailStr, Field, ValidationError, field_validator

# ── 1. Enums ───────────────────────────────────────────────────────────────────


class SeniorityLevel(IntEnum):
    """Ordered seniority scale shared by generators and labeler."""

    ENTRY = 0
    MID = 1
    SENIOR = 2
    LEAD = 3
    EXECUTIVE = 4

    @classmethod
    def from_years(cls, years: float) -> "SeniorityLevel":
        if years < 2:
            return cls.ENTRY
        if years < 5:
            return cls.MID
        if years < 8:
            return cls.SENIOR
        if years < 12:
            return cls.LEAD
        return cls.EXECUTIVE

    @classmethod
    def from_title(cls, title: str) -> "SeniorityLevel":
        t = title.lower()
        if any(k in t for k in ("executive", "director", "vp", "c-level", "chief")):
            return cls.EXECUTIVE
        if any(k in t for k in ("lead", "principal")):
            return cls.LEAD
        if any(k in t for k in ("senior", " sr ")):
            return cls.SENIOR
        if any(k in t for k in ("junior", " jr ", "entry")):
            return cls.ENTRY
        return cls.MID

    def below(self, steps: int = 1) -> "SeniorityLevel":
        return SeniorityLevel(max(0, self.value - steps))

    def opposite(self) -> "SeniorityLevel":
        if self.value <= 1:
            return SeniorityLevel(min(self.value + 2, 4))
        return SeniorityLevel(max(self.value - 2, 0))

    @property
    def label(self) -> str:
        return self.name.capitalize()

    @property
    def min_years(self) -> int:
        return {0: 1, 1: 3, 2: 6, 3: 8, 4: 10}[self.value]


class FitLevel(StrEnum):
    """Controlled fit levels between a resume and a job description."""

    EXCELLENT = "excellent"  # 80%+ skill overlap
    GOOD = "good"  # 60–80%
    PARTIAL = "partial"  # 40–60%
    POOR = "poor"  # 20–40%
    MISMATCH = "mismatch"  # <20%


# ── 2. Resume models ───────────────────────────────────────────────────────────


class ContactInfo(BaseModel):
    name: str = Field(..., min_length=1, description="Full name of the candidate")
    email: EmailStr = Field(..., description="Email address")
    phone: str = Field(..., min_length=10, description="Phone number")
    location: str = Field(..., description="City, State or City, Country")
    linkedin: str | None = Field(None, description="LinkedIn profile URL")
    portfolio: str | None = Field(None, description="Portfolio or personal website URL")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        cleaned = "".join(c for c in v if c.isdigit() or c in "+-(). ")
        if len("".join(c for c in cleaned if c.isdigit())) < 10:
            raise ValueError("Phone number must have at least 10 digits")
        return v


class Education(BaseModel):
    degree: str = Field(..., description="Degree type and major (e.g., 'B.S. Computer Science')")
    institution: str = Field(..., description="Name of the educational institution")
    graduation_date: date = Field(..., description="Graduation date")
    gpa: float | None = Field(None, ge=0.0, le=4.0, description="GPA on 4.0 scale")
    relevant_coursework: list[str] | None = Field(default_factory=lambda: [])

    @field_validator("graduation_date", mode="before")
    @classmethod
    def parse_graduation_date(cls, v):
        if isinstance(v, str):
            try:
                return date.fromisoformat(v)
            except ValueError:
                for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%B %Y", "%b %Y"]:
                    try:
                        return datetime.strptime(v, fmt).date()
                    except ValueError:
                        continue
                raise ValueError(f"Unable to parse date: {v}") from None
        return v


class Experience(BaseModel):
    company: str = Field(..., description="Company name")
    title: str = Field(..., description="Job title")
    start_date: date = Field(..., description="Start date of employment")
    end_date: date | None = Field(None, description="End date (None if current)")
    responsibilities: list[str] = Field(default_factory=list, min_length=1)
    achievements: list[str] = Field(default_factory=list)

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def parse_date(cls, v):
        if v is None:
            return v
        if isinstance(v, str):
            try:
                return date.fromisoformat(v)
            except ValueError:
                for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%B %Y", "%b %Y"]:
                    try:
                        return datetime.strptime(v, fmt).date()
                    except ValueError:
                        continue
                raise ValueError(f"Unable to parse date: {v}") from None
        return v

    @field_validator("end_date")
    @classmethod
    def validate_end_date(cls, v, info):
        if v is not None and "start_date" in info.data:
            start = info.data["start_date"]
            if start and v < start:
                raise ValueError("end_date must be after start_date")
        return v


class Skill(BaseModel):
    name: str = Field(..., description="Skill name")
    proficiency_level: str = Field(
        ..., description="Proficiency: Beginner, Intermediate, Advanced, or Expert"
    )
    years_experience: float | None = Field(None, ge=0)

    @field_validator("proficiency_level")
    @classmethod
    def validate_proficiency(cls, v: str) -> str:
        valid_levels = {"beginner", "intermediate", "advanced", "expert"}
        if v.lower() not in valid_levels:
            raise ValueError(f"Proficiency level must be one of: {valid_levels}")
        return v.capitalize()


class ResumeMetadata(BaseModel):
    trace_id: str | None = Field(None, description="Unique trace ID")
    generated_at: datetime | None = Field(None, description="Generation timestamp")
    prompt_template: str | None = Field(None, description="Prompt template used")
    target_industry: str | None = None
    target_seniority: str | None = None
    fit_level: FitLevel | None = Field(None, description="Fit level vs target job")
    target_job_trace_id: str | None = None


class Resume(BaseModel):
    contact: ContactInfo = Field(..., description="Contact information")
    summary: str | None = Field(None, max_length=500, description="Professional summary")
    education: list[Education] = Field(default_factory=list, min_length=1)
    experience: list[Experience] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list, min_length=1)
    certifications: list[str] | None = Field(default_factory=lambda: [])
    languages: list[str] | None = Field(default_factory=lambda: [])
    metadata: ResumeMetadata | None = Field(default=None)


# ── 3. Job description models ──────────────────────────────────────────────────


class Company(BaseModel):
    name: str = Field(..., min_length=1, description="Company name")
    industry: str = Field(..., description="Industry sector")
    size: str = Field(..., description="Startup, Small, Medium, Large, or Enterprise")
    location: str = Field(..., description="Company location or 'Remote'")

    @field_validator("size")
    @classmethod
    def validate_size(cls, v: str) -> str:
        valid_sizes = {"startup", "small", "medium", "large", "enterprise"}
        if v.lower() not in valid_sizes:
            raise ValueError(f"Company size must be one of: {valid_sizes}")
        return v.capitalize()


class Requirements(BaseModel):
    required_skills: list[str] = Field(default_factory=list, min_length=3)
    preferred_skills: list[str] = Field(default_factory=list)
    education_requirements: str = Field(..., description="Minimum education requirement")
    experience_years: int = Field(..., ge=1, le=30)
    experience_level: str = Field(..., description="Entry, Mid, Senior, Lead, or Executive")

    @field_validator("experience_level")
    @classmethod
    def validate_experience_level(cls, v: str) -> str:
        valid_levels = {"entry", "mid", "senior", "lead", "executive"}
        if v.lower() not in valid_levels:
            raise ValueError(f"Experience level must be one of: {valid_levels}")
        return v.capitalize()


class JobDescriptionMetadata(BaseModel):
    trace_id: str | None = Field(None, description="Unique trace ID")
    generated_at: datetime | None = Field(None, description="Generation timestamp")
    prompt_template: str | None = Field(None, description="Prompt template used")
    is_niche_role: bool | None = Field(None, description="Niche/specialized role flag")


class JobDescription(BaseModel):
    title: str = Field(..., min_length=1, description="Job title")
    company: Company
    description: str = Field(..., min_length=50, description="Detailed job description")
    requirements: Requirements
    responsibilities: list[str] = Field(default_factory=list, min_length=1)
    benefits: list[str] = Field(default_factory=list)
    salary_range: str | None = None
    remote_policy: str = Field("On-site", description="Remote, Hybrid, or On-site")
    employment_type: str = Field(
        "Full-time", description="Full-time, Part-time, Contract, Internship"
    )
    metadata: JobDescriptionMetadata | None = Field(default=None)

    @field_validator("remote_policy")
    @classmethod
    def validate_remote_policy(cls, v: str) -> str:
        valid = {"remote", "hybrid", "on-site", "onsite"}
        if v.lower().replace("-", "") not in {p.replace("-", "") for p in valid}:
            raise ValueError("Remote policy must be one of: Remote, Hybrid, On-site")
        return v.capitalize()

    @field_validator("employment_type")
    @classmethod
    def validate_employment_type(cls, v: str) -> str:
        valid = {"full-time", "fulltime", "part-time", "parttime", "contract", "internship"}
        if v.lower().replace("-", "") not in {t.replace("-", "") for t in valid}:
            raise ValueError(
                "Employment type must be one of: Full-time, Part-time, Contract, Internship"
            )
        return v.capitalize()


# ── 4. Pair model ──────────────────────────────────────────────────────────────


class ResumeJobPairMetadata(BaseModel):
    trace_id: str | None = Field(None, description="Unique trace ID for this pair")
    generated_at: datetime | None = None
    fit_level: str | None = Field(None, description="excellent, good, partial, poor, mismatch")


class ResumeJobPair(BaseModel):
    """A matched resume + job description with controlled fit level for training data."""

    resume: Resume
    job_description: JobDescription
    match_score: float | None = Field(None, ge=0.0, le=1.0)
    match_analysis: str | None = None
    metadata: ResumeJobPairMetadata | None = Field(default=None)


# ── 5. Validation types ────────────────────────────────────────────────────────


@dataclass
class ValidationError_:
    """Detailed validation error information."""

    field: str
    error_type: str
    message: str
    input_value: Any = None

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "error_type": self.error_type,
            "message": self.message,
            "input_value": str(self.input_value)[:100] if self.input_value else None,
        }


@dataclass
class ValidationResult:
    """Result of a validation operation."""

    is_valid: bool
    data: BaseModel | None = None
    raw_data: dict | None = None
    errors: list[ValidationError_] = dc_field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "error_count": len(self.errors),
            "errors": [e.to_dict() for e in self.errors],
        }


class SchemaValidator:
    """Validate Resume, JobDescription, and ResumeJobPair against Pydantic schemas."""

    def __init__(self) -> None:
        self.validation_stats: dict = {
            "total": 0,
            "valid": 0,
            "invalid": 0,
            "errors_by_type": {},
            "errors_by_field": {},
        }

    def validate_resume(self, data: dict) -> ValidationResult:
        return self._validate(data, Resume)

    def validate_job(self, data: dict) -> ValidationResult:
        return self._validate(data, JobDescription)

    def validate_pair(self, data: dict) -> ValidationResult:
        return self._validate(data, ResumeJobPair)

    def _validate(self, data: dict, schema: type[BaseModel]) -> ValidationResult:
        self.validation_stats["total"] += 1
        with logfire.span("validate_data", schema=schema.__name__):
            try:
                validated = schema.model_validate(data)
                self.validation_stats["valid"] += 1
                logfire.info("Validation successful", schema=schema.__name__)
                return ValidationResult(is_valid=True, data=validated, raw_data=data)
            except ValidationError as e:
                self.validation_stats["invalid"] += 1
                errors = self._parse_errors(e)
                for err in errors:
                    self.validation_stats["errors_by_type"][err.error_type] = (
                        self.validation_stats["errors_by_type"].get(err.error_type, 0) + 1
                    )
                    self.validation_stats["errors_by_field"][err.field] = (
                        self.validation_stats["errors_by_field"].get(err.field, 0) + 1
                    )
                logfire.warning(
                    "Validation failed", schema=schema.__name__, error_count=len(errors)
                )
                return ValidationResult(is_valid=False, raw_data=data, errors=errors)

    def _parse_errors(self, exc: ValidationError) -> list[ValidationError_]:
        return [
            ValidationError_(
                field=".".join(str(loc) for loc in e["loc"]),
                error_type=e["type"],
                message=e["msg"],
                input_value=e.get("input"),
            )
            for e in exc.errors()
        ]

    def validate_batch(
        self,
        data_list: list[dict],
        data_type: str = "resume",
    ) -> tuple[list[ValidationResult], dict]:
        fn = {
            "resume": self.validate_resume,
            "job": self.validate_job,
            "pair": self.validate_pair,
        }.get(data_type)
        if not fn:
            raise ValueError(f"Invalid data_type: {data_type}")
        with logfire.span("validate_batch", count=len(data_list), data_type=data_type):
            results = [fn(d) for d in data_list]
        valid = sum(1 for r in results if r.is_valid)
        summary = {
            "total": len(results),
            "valid": valid,
            "invalid": len(results) - valid,
            "success_rate": valid / len(results) if results else 0,
        }
        logfire.info("Batch validation complete", **summary)
        return results, summary

    def get_stats(self) -> dict:
        stats = self.validation_stats.copy()
        stats["success_rate"] = stats["valid"] / stats["total"] if stats["total"] > 0 else 0
        return stats

    def reset_stats(self) -> None:
        self.validation_stats = {
            "total": 0,
            "valid": 0,
            "invalid": 0,
            "errors_by_type": {},
            "errors_by_field": {},
        }

    def save_results(
        self,
        results: list[ValidationResult],
        output_dir: str = "data/validated",
        filename: str = "validation_results.json",
    ) -> Path:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        file_path = output_path / filename
        with open(file_path, "w") as f:
            json.dump([r.to_dict() for r in results], f, indent=2)
        logfire.info(f"Saved {len(results)} validation results to {file_path}")
        return file_path
