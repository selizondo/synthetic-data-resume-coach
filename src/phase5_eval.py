"""Phase 5 — Label quality analysis.

Reads failure_labels_<run>.jsonl (always present) and optionally
llm_judgments_<run>.jsonl (present when --enable-llm-judge was used).
Produces label_quality_<run>.json with four diagnostics:

  - threshold_sensitivity: pass rate vs Jaccard threshold sweep
  - fit_level_stats: per-level pass rate + failure breakdown
  - dimension_correlations: Pearson r between the 5 binary failure flags
  - llm_agreement: Cohen's kappa on overlapping dimensions (if judge data exists)
"""

import json
from pathlib import Path

import logfire

from .analysis.eval_quality import LabelQualityAnalyzer, LabelQualityReport
from .utils.storage import load_jsonl


def run_eval_quality_phase(
    run_label: str,
    output_dir: str = "data",
) -> LabelQualityReport:
    labeled_dir = Path(output_dir) / "labeled"
    label_file = labeled_dir / f"failure_labels_{run_label}.jsonl"
    judgment_file = labeled_dir / f"llm_judgments_{run_label}.jsonl"

    if not label_file.exists():
        raise FileNotFoundError(
            f"No failure labels found for run '{run_label}'. "
            f"Expected: {label_file}\n"
            "Run phases 1–3 first, or pass the correct --resume label."
        )

    with logfire.span("eval_quality_phase", run_label=run_label):
        labels = load_jsonl(label_file)
        judgments = load_jsonl(judgment_file) if judgment_file.exists() else None

        logfire.info(
            "Loaded label data",
            n_labels=len(labels),
            n_judgments=len(judgments) if judgments else 0,
        )

        report = LabelQualityAnalyzer().analyze(labels, judgments, run_label)

        out_file = labeled_dir / f"label_quality_{run_label}.json"
        out_file.write_text(report.model_dump_json(indent=2))

        logfire.info(
            "Label quality report saved",
            path=str(out_file),
            monotonic_valid=report.monotonic_ordering_valid,
            violations=len(report.ordering_violations),
        )

    _print_summary(report)
    return report


def _print_summary(report: LabelQualityReport) -> None:
    w = 58
    print(f"\n{'─' * w}")
    print(f"  LABEL QUALITY — {report.run_label}")
    print(f"  {report.total_pairs} pairs analyzed")
    print(f"{'─' * w}")

    print("\n  Threshold Sensitivity (pass rate by Jaccard cutoff):")
    for t, rate in report.threshold_sensitivity.items():
        bar = "█" * int(rate * 30)
        print(f"    {t}  {bar:<30}  {rate:.1%}")

    print("\n  Fit-Level Stratification:")
    from .analysis.eval_quality import FIT_LEVEL_ORDER
    for lvl in FIT_LEVEL_ORDER:
        if lvl not in report.fit_level_stats:
            continue
        s = report.fit_level_stats[lvl]
        bar = "█" * int(s.pass_rate * 30)
        print(f"    {lvl:<10}  {bar:<30}  {s.pass_rate:.1%}  (n={s.n})")

    if report.ordering_violations:
        print(f"\n  ⚠ Monotonic ordering violated:")
        for v in report.ordering_violations:
            print(f"    {v}")
    else:
        print("\n  ✓ Fit-level ordering is monotonically decreasing")

    if report.llm_agreement:
        ag = report.llm_agreement
        print(f"\n  LLM Agreement (Cohen's κ, n={ag.n_pairs}):")
        print(f"    hallucination:    κ={ag.hallucination_kappa:.3f}")
        print(f"    awkward_language: κ={ag.awkward_language_kappa:.3f}")

    print(f"{'─' * w}\n")
