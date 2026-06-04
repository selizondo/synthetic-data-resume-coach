"""Tests for src/analysis/eval_quality.py — all offline, no LLM calls."""

import uuid

import pytest

from src.analysis.eval_quality import (
    BINARY_DIMS,
    LabelQualityAnalyzer,
    _cohen_kappa_binary,
)

# ── Fixtures ───────────────────────────────────────────────────────────────────


def _label(
    fit_level="good",
    overlap=0.7,
    exp_mm=0,
    sen_mm=0,
    miss=0,
    hall=0,
    awk=0,
    trace_id=None,
) -> dict:
    return {
        "trace_id": trace_id or str(uuid.uuid4()),
        "skills_overlap_ratio": overlap,
        "fit_level": fit_level,
        "experience_mismatch": exp_mm,
        "seniority_mismatch": sen_mm,
        "missing_core_skill": miss,
        "hallucinated_skill": hall,
        "awkward_language_flag": awk,
    }


def _judgment(trace_id: str, has_hall: bool, has_awk: bool) -> dict:
    return {
        "trace_id": trace_id,
        "has_hallucinations": has_hall,
        "has_awkward_language": has_awk,
        "overall_quality_score": 0.8,
    }


# ── TestThresholdSensitivity ───────────────────────────────────────────────────


class TestThresholdSensitivity:
    def setup_method(self):
        self.analyzer = LabelQualityAnalyzer()

    def test_all_pass_produces_declining_curve(self):
        labels = [_label(overlap=0.9) for _ in range(20)]
        result = self.analyzer._threshold_sensitivity(labels, [0.2, 0.5, 0.8])
        assert result["0.2"] >= result["0.5"] >= result["0.8"]

    def test_all_fail_overlap_returns_zeros(self):
        labels = [_label(overlap=0.1) for _ in range(10)]
        result = self.analyzer._threshold_sensitivity(labels, [0.2, 0.5, 0.8])
        assert all(v == 0.0 for v in result.values())

    def test_threshold_at_exact_value_counts_pair(self):
        # One pair with overlap=0.5 — passes at ≤0.5, fails at >0.5
        labels = [_label(overlap=0.5)]
        result = self.analyzer._threshold_sensitivity(labels, [0.5, 0.6])
        assert result["0.5"] == 1.0
        assert result["0.6"] == 0.0

    def test_empty_labels_returns_zeros(self):
        result = self.analyzer._threshold_sensitivity([], [0.3, 0.5])
        assert all(v == 0.0 for v in result.values())


# ── TestFitLevelStats ──────────────────────────────────────────────────────────


class TestFitLevelStats:
    def setup_method(self):
        self.analyzer = LabelQualityAnalyzer()

    def test_correct_grouping_and_pass_rate(self):
        labels = (
            [_label(fit_level="excellent", overlap=0.9)] * 8
            + [_label(fit_level="excellent", overlap=0.1)] * 2
            + [_label(fit_level="mismatch", overlap=0.1)] * 5
        )
        stats = self.analyzer._fit_level_stats(labels)
        assert "excellent" in stats
        assert "mismatch" in stats
        assert stats["excellent"].n == 10
        assert stats["excellent"].pass_rate == pytest.approx(0.8)
        assert stats["mismatch"].pass_rate == pytest.approx(0.0)

    def test_none_fit_level_excluded(self):
        labels = [_label(fit_level=None), _label(fit_level="good")]
        # Inject None directly since helper sets a value
        labels[0]["fit_level"] = None
        stats = self.analyzer._fit_level_stats(labels)
        assert None not in stats
        assert "good" in stats


# ── TestMonotonicOrdering ──────────────────────────────────────────────────────


class TestMonotonicOrdering:
    def setup_method(self):
        self.analyzer = LabelQualityAnalyzer()

    def test_detects_inversion(self):
        from src.analysis.eval_quality import FitLevelStats

        stats = {
            "excellent": FitLevelStats(n=10, pass_rate=0.60, failure_breakdown={}),
            "good": FitLevelStats(n=10, pass_rate=0.72, failure_breakdown={}),  # inversion
        }
        valid, violations = self.analyzer._check_monotonic_ordering(stats)
        assert not valid
        assert len(violations) == 1
        assert "good" in violations[0]

    def test_valid_ordering_passes(self):
        from src.analysis.eval_quality import FitLevelStats

        stats = {
            "excellent": FitLevelStats(n=10, pass_rate=0.90, failure_breakdown={}),
            "good": FitLevelStats(n=10, pass_rate=0.70, failure_breakdown={}),
            "partial": FitLevelStats(n=10, pass_rate=0.40, failure_breakdown={}),
            "poor": FitLevelStats(n=10, pass_rate=0.15, failure_breakdown={}),
            "mismatch": FitLevelStats(n=10, pass_rate=0.05, failure_breakdown={}),
        }
        valid, violations = self.analyzer._check_monotonic_ordering(stats)
        assert valid
        assert violations == []


# ── TestDimensionCorrelations ──────────────────────────────────────────────────


class TestDimensionCorrelations:
    def setup_method(self):
        self.analyzer = LabelQualityAnalyzer()

    def test_perfect_positive_correlation(self):
        # exp_mm and sen_mm always identical → r = 1.0
        labels = [_label(exp_mm=v, sen_mm=v) for v in [0, 1, 0, 1, 1, 0, 1, 0]]
        matrix = self.analyzer._dimension_correlations(labels)
        r = matrix["experience_mismatch"]["seniority_mismatch"]
        assert r == pytest.approx(1.0, abs=1e-3)

    def test_zero_variance_column_returns_zero(self):
        # All labels have experience_mismatch=0 — zero variance → r=0.0
        labels = [_label(exp_mm=0, sen_mm=i % 2) for i in range(10)]
        matrix = self.analyzer._dimension_correlations(labels)
        r = matrix["experience_mismatch"]["seniority_mismatch"]
        assert r == 0.0

    def test_diagonal_is_one(self):
        labels = [_label() for _ in range(5)]
        matrix = self.analyzer._dimension_correlations(labels)
        for dim in BINARY_DIMS:
            assert matrix[dim][dim] == pytest.approx(1.0)


# ── TestCohenKappa ─────────────────────────────────────────────────────────────


class TestCohenKappa:
    def setup_method(self):
        self.analyzer = LabelQualityAnalyzer()

    def test_perfect_agreement_returns_one(self):
        # Both raters identical
        assert _cohen_kappa_binary([0, 1, 0, 1, 1], [0, 1, 0, 1, 1]) == pytest.approx(1.0)

    def test_total_disagreement_returns_negative(self):
        # Alternating opposite labels with balanced class rates → pe=0.5, po=0 → kappa=-1
        assert _cohen_kappa_binary([0, 1, 0, 1], [1, 0, 1, 0]) < 0.0

    def test_fewer_than_min_pairs_returns_none(self):
        tids = [str(uuid.uuid4()) for _ in range(4)]
        labels = [_label(hall=1, trace_id=tid) for tid in tids]
        judgments = [_judgment(tid, has_hall=True, has_awk=False) for tid in tids]
        result = self.analyzer._cohen_kappa(labels, judgments)
        assert result is None

    def test_sufficient_pairs_returns_stats(self):
        tids = [str(uuid.uuid4()) for _ in range(10)]
        labels = [_label(hall=1, awk=0, trace_id=tid) for tid in tids]
        judgments = [_judgment(tid, has_hall=True, has_awk=False) for tid in tids]
        result = self.analyzer._cohen_kappa(labels, judgments)
        assert result is not None
        assert result.n_pairs == 10
        assert result.hallucination_kappa == pytest.approx(1.0)


# ── TestFullAnalyze ────────────────────────────────────────────────────────────


class TestFullAnalyze:
    def test_integration_with_synthetic_data(self):
        analyzer = LabelQualityAnalyzer()
        labels = (
            [_label(fit_level="excellent", overlap=0.9)] * 8
            + [_label(fit_level="excellent", overlap=0.1)] * 2
            + [_label(fit_level="good", overlap=0.75)] * 6
            + [_label(fit_level="good", overlap=0.3)] * 4
            + [_label(fit_level="mismatch", overlap=0.05, exp_mm=1)] * 10
        )
        report = analyzer.analyze(labels, run_label="test_run")

        assert report.total_pairs == 30
        assert report.run_label == "test_run"
        assert "0.5" in report.threshold_sensitivity
        assert "excellent" in report.fit_level_stats
        assert "mismatch" in report.fit_level_stats
        assert "experience_mismatch" in report.dimension_correlations
        assert report.llm_agreement is None  # no judgments passed
        # Excellent should have higher pass rate than mismatch
        assert (
            report.fit_level_stats["excellent"].pass_rate
            > report.fit_level_stats["mismatch"].pass_rate
        )
