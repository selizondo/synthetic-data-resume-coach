"""Phase 2 — Schema validation and error categorization."""

import json
from collections import defaultdict
from pathlib import Path

from .schema import JobDescription, Resume, SchemaValidator
from .utils.storage import save_jsonl


def _categorize_error(error_type: str, field: str) -> str:
    """Map a Pydantic error type + field to one of the four spec categories."""
    t = error_type.lower()
    f = field.lower()
    if "missing" in t or "required" in t:
        return "missing_required_fields"
    if any(k in f for k in ("date", "start_date", "end_date", "graduation")):
        if "order" in t or "after" in t or "before" in t:
            return "logical_inconsistencies"
        return "format_violations"
    if any(k in f for k in ("email", "phone", "gpa")):
        return "format_violations"
    if "type" in t or "int" in t or "float" in t or "str" in t:
        return "type_mismatches"
    return "format_violations"


def run_validation_phase(
    jobs: list[JobDescription],
    resumes: list[Resume],
    output_dir: str,
    run_label: str,
    generate_heatmaps: bool = True,
) -> dict:
    """Run Pydantic schema validation on generated jobs and resumes.

    Args:
        jobs: Generated job descriptions.
        resumes: Generated resumes.
        output_dir: Base output directory.
        run_label: Timestamp label used for output filenames.

    Returns:
        Dict with keys: resume_results, job_results, resume_summary,
        job_summary, invalid_resumes, invalid_jobs, files.
    """
    validator = SchemaValidator()
    validated_dir = Path(output_dir) / "validated"
    validated_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 2.1: Validate resumes ────────────────────────────────────────────
    print(f"  Validating {len(resumes)} resumes...")
    resume_data = [r.model_dump(mode="json") for r in resumes]
    resume_results, resume_summary = validator.validate_batch(resume_data, data_type="resume")

    valid_count = resume_summary.get("valid", 0)
    total_count = resume_summary.get("total", len(resumes))
    rate = valid_count / total_count if total_count else 0
    status = "✓" if rate >= 0.9 else "✗"
    print(
        f"  {status} Resumes: {valid_count}/{total_count} valid ({rate * 100:.1f}%) — target >90%"
    )

    # ── Step 2.2: Validate jobs ────────────────────────────────────────────────
    print(f"  Validating {len(jobs)} job descriptions...")
    job_data = [j.model_dump(mode="json") for j in jobs]
    job_results, job_summary = validator.validate_batch(job_data, data_type="job")

    valid_jobs = job_summary.get("valid", 0)
    total_jobs = job_summary.get("total", len(jobs))
    job_rate = valid_jobs / total_jobs if total_jobs else 0
    status = "✓" if job_rate >= 0.9 else "✗"
    print(f"  {status} Jobs: {valid_jobs}/{total_jobs} valid ({job_rate * 100:.1f}%) — target >90%")

    # ── Step 2.3: Save invalid records ────────────────────────────────────────
    files: dict[str, str] = {}
    labeled_dir = Path(output_dir) / "labeled"
    labeled_dir.mkdir(parents=True, exist_ok=True)

    invalid_resumes = [r for r in resume_results if not r.is_valid]
    invalid_jobs = [r for r in job_results if not r.is_valid]

    if invalid_resumes or invalid_jobs:
        invalid_data = [{"type": "resume", **r.to_dict()} for r in invalid_resumes] + [
            {"type": "job", **r.to_dict()} for r in invalid_jobs
        ]
        invalid_file = labeled_dir / f"invalid_{run_label}.jsonl"
        save_jsonl(invalid_data, invalid_file)
        files["invalid_records"] = str(invalid_file)
        print(f"  Saved → {invalid_file}")

    print(
        f"\n  Phase 2 complete: {len(invalid_resumes)} invalid resumes, {len(invalid_jobs)} invalid jobs"
    )

    # ── Step 2.3b: Write validated_data summary ───────────────────────────────
    valid_resume_ids = [
        r.raw_data.get("metadata", {}).get("trace_id") for r in resume_results if r.is_valid
    ]
    valid_job_ids = [
        r.raw_data.get("metadata", {}).get("trace_id") for r in job_results if r.is_valid
    ]
    validated_summary = {
        "run_label": run_label,
        "resumes": {
            "total": len(resumes),
            "valid": len(valid_resume_ids),
            "invalid": len(invalid_resumes),
            "rate": resume_summary.get("valid_rate", 1.0),
        },
        "jobs": {
            "total": len(jobs),
            "valid": len(valid_job_ids),
            "invalid": len(invalid_jobs),
            "rate": job_summary.get("valid_rate", 1.0),
        },
        "valid_resume_trace_ids": valid_resume_ids,
        "valid_job_trace_ids": valid_job_ids,
    }
    validated_file = validated_dir / f"validated_data_{run_label}.json"
    validated_file.write_text(json.dumps(validated_summary, indent=2, default=str))
    files["validated_data"] = str(validated_file)
    print(f"  Saved → {validated_file}")

    # ── Step 2.3c: Write schema_failure_modes summary ─────────────────────────
    error_categories: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "fields": defaultdict(int)}
    )
    all_invalid = [("resume", r) for r in invalid_resumes] + [("job", r) for r in invalid_jobs]
    for _dtype, result in all_invalid:
        for err in result.errors:
            category = _categorize_error(err.error_type, err.field)
            error_categories[category]["count"] += 1
            error_categories[category]["fields"][err.field] += 1

    failure_modes = {
        cat: {
            "count": v["count"],
            "top_fields": sorted(v["fields"].items(), key=lambda x: x[1], reverse=True)[:3],
        }
        for cat, v in error_categories.items()
    }
    schema_failure_file = validated_dir / f"schema_failure_modes_{run_label}.json"
    schema_failure_file.write_text(
        json.dumps(
            {
                "run_label": run_label,
                "total_invalid_records": len(all_invalid),
                "failure_modes": failure_modes,
                "_note": (
                    "Empty failure_modes means all records passed Pydantic validation. "
                    "instructor enforces the schema at LLM output time, preventing schema "
                    "errors regardless of model. See docs/correction_loop_proof.md for "
                    "correction loop results on synthetically injected failures."
                )
                if not failure_modes
                else None,
            },
            indent=2,
            default=str,
        )
    )
    files["schema_failure_modes"] = str(schema_failure_file)
    print(f"  Saved → {schema_failure_file}")

    # ── Step 2.4: Generate field-level validation heatmaps ───────────────────
    if generate_heatmaps:
        from .analysis.heatmap import HeatmapGenerator

        viz_dir = validated_dir / "visualizations"
        hm = HeatmapGenerator(output_dir=str(viz_dir))
        heatmap_tasks = [
            (
                "resume_validation_heatmap",
                lambda: hm.create_field_validation_heatmap(
                    resume_results,
                    data_type="resume",
                    filename=f"resume_field_validation_{run_label}.png",
                ),
            ),
            (
                "job_validation_heatmap",
                lambda: hm.create_field_validation_heatmap(
                    job_results, data_type="job", filename=f"job_field_validation_{run_label}.png"
                ),
            ),
        ]
        for key, fn in heatmap_tasks:
            try:
                files[key] = str(fn())
            except Exception as exc:
                print(f"  Warning: heatmap '{key}' failed: {exc}")
        heatmap_count = sum(
            1 for k in ("resume_validation_heatmap", "job_validation_heatmap") if k in files
        )
        if heatmap_count:
            print(f"  Generated {heatmap_count} heatmaps → {viz_dir}")

    return {
        "resume_results": resume_results,
        "job_results": job_results,
        "resume_summary": resume_summary,
        "job_summary": job_summary,
        "invalid_resumes": invalid_resumes,
        "invalid_jobs": invalid_jobs,
        "files": files,
    }
