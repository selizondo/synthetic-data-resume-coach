"""Label quality analysis for the synthetic data pipeline.

Computes four diagnostics from failure_labels_<run>.jsonl:

  1. Threshold sensitivity — pass rate as Jaccard threshold varies 0.2→0.8.
     Validates that 0.5 is in a stable region, not on a cliff edge.

  2. Fit-level stratification — per-level pass rate and failure breakdown.
     Validates the LLM is following distribution instructions (Excellent
     should pass consistently; Mismatch should fail consistently).

  3. Dimension correlations — Pearson r between all pairs of the 5 binary
     failure flags. High r indicates redundant dimensions.

  4. LLM agreement (optional) — Cohen's kappa on the two overlapping
     binary dimensions (hallucination, awkward language) when
     llm_judgments_<run>.jsonl is available.
"""

import math
from datetime import UTC, datetime

from pydantic import BaseModel, Field

BINARY_DIMS = [
    "experience_mismatch",
    "seniority_mismatch",
    "missing_core_skill",
    "hallucinated_skill",
    "awkward_language_flag",
]

# Expected monotonic order: pass rate should decrease left → right.
FIT_LEVEL_ORDER = ["excellent", "good", "partial", "poor", "mismatch"]

DEFAULT_THRESHOLDS = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]

MIN_PAIRS_FOR_KAPPA = 5


# ── Pydantic report models ─────────────────────────────────────────────────────


class FitLevelStats(BaseModel):
    n: int
    pass_rate: float = Field(ge=0.0, le=1.0)
    failure_breakdown: dict[str, float]


class LLMAgreementStats(BaseModel):
    n_pairs: int
    hallucination_kappa: float
    awkward_language_kappa: float


class LabelQualityReport(BaseModel):
    run_label: str
    total_pairs: int
    generated_at: str
    threshold_sensitivity: dict[str, float]
    fit_level_stats: dict[str, FitLevelStats]
    dimension_correlations: dict[str, dict[str, float]]
    monotonic_ordering_valid: bool
    ordering_violations: list[str]
    llm_agreement: LLMAgreementStats | None = None


# ── Helpers ────────────────────────────────────────────────────────────────────


def _pair_passes(label: dict, overlap_threshold: float) -> bool:
    if label.get("skills_overlap_ratio", 0.0) < overlap_threshold:
        return False
    return all(label.get(dim, 0) == 0 for dim in BINARY_DIMS)


def _pearson_r(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=False))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0.0 or dy == 0.0:
        return 0.0
    return round(num / (dx * dy), 4)


def _cohen_kappa_binary(rule_vals: list[int], judge_vals: list[int]) -> float:
    """Cohen's kappa for two binary raters."""
    n = len(rule_vals)
    if n == 0:
        return 0.0
    agree = sum(r == j for r, j in zip(rule_vals, judge_vals, strict=False))
    po = agree / n
    rule_pos = sum(rule_vals) / n
    judge_pos = sum(judge_vals) / n
    pe = rule_pos * judge_pos + (1 - rule_pos) * (1 - judge_pos)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return round((po - pe) / (1 - pe), 4)


# ── Analyzer ───────────────────────────────────────────────────────────────────


class LabelQualityAnalyzer:
    """Compute label quality diagnostics from persisted failure-label records."""

    def analyze(
        self,
        labels: list[dict],
        judgments: list[dict] | None = None,
        run_label: str = "",
    ) -> LabelQualityReport:
        threshold_sensitivity = self._threshold_sensitivity(labels, DEFAULT_THRESHOLDS)
        fit_level_stats = self._fit_level_stats(labels)
        monotonic_valid, violations = self._check_monotonic_ordering(fit_level_stats)
        dimension_correlations = self._dimension_correlations(labels)
        llm_agreement = self._cohen_kappa(labels, judgments) if judgments else None

        return LabelQualityReport(
            run_label=run_label,
            total_pairs=len(labels),
            generated_at=datetime.now(UTC).isoformat(),
            threshold_sensitivity=threshold_sensitivity,
            fit_level_stats=fit_level_stats,
            dimension_correlations=dimension_correlations,
            monotonic_ordering_valid=monotonic_valid,
            ordering_violations=violations,
            llm_agreement=llm_agreement,
        )

    def _threshold_sensitivity(
        self, labels: list[dict], thresholds: list[float]
    ) -> dict[str, float]:
        if not labels:
            return {str(t): 0.0 for t in thresholds}
        result = {}
        for t in thresholds:
            passes = sum(1 for lb in labels if _pair_passes(lb, t))
            result[str(t)] = round(passes / len(labels), 4)
        return result

    def _fit_level_stats(self, labels: list[dict]) -> dict[str, FitLevelStats]:
        groups: dict[str, list[dict]] = {}
        for lb in labels:
            lvl = lb.get("fit_level")
            if lvl is None:
                continue
            groups.setdefault(lvl, []).append(lb)

        stats: dict[str, FitLevelStats] = {}
        for lvl, group in groups.items():
            n = len(group)
            passes = sum(1 for lb in group if _pair_passes(lb, 0.5))
            breakdown = {
                dim: round(sum(lb.get(dim, 0) for lb in group) / n, 4) for dim in BINARY_DIMS
            }
            stats[lvl] = FitLevelStats(
                n=n,
                pass_rate=round(passes / n, 4),
                failure_breakdown=breakdown,
            )
        return stats

    def _check_monotonic_ordering(self, stats: dict[str, FitLevelStats]) -> tuple[bool, list[str]]:
        violations: list[str] = []
        present = [lvl for lvl in FIT_LEVEL_ORDER if lvl in stats]
        for i in range(1, len(present)):
            prev, curr = present[i - 1], present[i]
            prev_rate = stats[prev].pass_rate
            curr_rate = stats[curr].pass_rate
            if curr_rate > prev_rate:
                violations.append(f"{curr}({curr_rate:.2f}) > {prev}({prev_rate:.2f})")
        return len(violations) == 0, violations

    def _dimension_correlations(self, labels: list[dict]) -> dict[str, dict[str, float]]:
        cols: dict[str, list[float]] = {
            dim: [float(lb.get(dim, 0)) for lb in labels] for dim in BINARY_DIMS
        }
        matrix: dict[str, dict[str, float]] = {}
        for d1 in BINARY_DIMS:
            matrix[d1] = {}
            for d2 in BINARY_DIMS:
                matrix[d1][d2] = 1.0 if d1 == d2 else _pearson_r(cols[d1], cols[d2])
        return matrix

    def _cohen_kappa(self, labels: list[dict], judgments: list[dict]) -> LLMAgreementStats | None:
        # Build lookup: trace_id → judgment
        j_by_id = {j["trace_id"]: j for j in judgments if "trace_id" in j}

        hall_rule, hall_judge = [], []
        awk_rule, awk_judge = [], []

        for lb in labels:
            tid = lb.get("trace_id")
            if tid not in j_by_id:
                continue
            j = j_by_id[tid]
            hall_rule.append(int(lb.get("hallucinated_skill", 0)))
            hall_judge.append(int(bool(j.get("has_hallucinations", False))))
            awk_rule.append(int(lb.get("awkward_language_flag", 0)))
            awk_judge.append(int(bool(j.get("has_awkward_language", False))))

        if len(hall_rule) < MIN_PAIRS_FOR_KAPPA:
            return None

        return LLMAgreementStats(
            n_pairs=len(hall_rule),
            hallucination_kappa=_cohen_kappa_binary(hall_rule, hall_judge),
            awkward_language_kappa=_cohen_kappa_binary(awk_rule, awk_judge),
        )
