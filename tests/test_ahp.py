# -*- coding: utf-8 -*-
"""Tests for the AHP (Analytic Hierarchy Process) weight-derivation module
(docs/research_v2.md section 3.3) — an alternative to asserting the scoring
weights directly, with a built-in mathematical consistency check."""

from pathlib import Path

import numpy as np
import pytest

from ahp import (
    build_comparison_matrix,
    compute_ahp_weights,
    compute_consistency_ratio,
    derive_weights_from_config,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REAL_CONFIG_PATH = PROJECT_ROOT / "config" / "ahp_pairwise_comparisons.yaml"


def _toy_config(**overrides):
    config = {
        "criteria": ["a", "b", "c"],
        "comparisons": [
            {"a": "a", "b": "b", "value": 1},
            {"a": "a", "b": "c", "value": 1},
            {"a": "b", "b": "c", "value": 1},
        ],
    }
    config.update(overrides)
    return config


class TestBuildComparisonMatrix:
    def test_identity_comparisons_produce_all_ones_matrix(self):
        matrix, criteria = build_comparison_matrix(_toy_config())
        assert criteria == ["a", "b", "c"]
        assert np.allclose(matrix, np.ones((3, 3)))

    def test_reciprocal_is_filled_in_automatically(self):
        config = _toy_config(comparisons=[
            {"a": "a", "b": "b", "value": 3},
            {"a": "a", "b": "c", "value": 1},
            {"a": "b", "b": "c", "value": 1},
        ])
        matrix, criteria = build_comparison_matrix(config)
        i, j = criteria.index("a"), criteria.index("b")
        assert matrix[i, j] == pytest.approx(3.0)
        assert matrix[j, i] == pytest.approx(1.0 / 3.0)

    def test_missing_pair_raises_clear_error(self):
        config = _toy_config(comparisons=[
            {"a": "a", "b": "b", "value": 1},
            {"a": "a", "b": "c", "value": 1},
            # missing (b, c)
        ])
        with pytest.raises(ValueError, match="b.*c|c.*b"):
            build_comparison_matrix(config)

    def test_duplicate_pair_raises_clear_error(self):
        config = _toy_config(comparisons=[
            {"a": "a", "b": "b", "value": 1},
            {"a": "a", "b": "b", "value": 2},
            {"a": "a", "b": "c", "value": 1},
            {"a": "b", "b": "c", "value": 1},
        ])
        with pytest.raises(ValueError, match="Duplicate"):
            build_comparison_matrix(config)

    def test_unknown_criterion_raises_clear_error(self):
        config = _toy_config(comparisons=[
            {"a": "a", "b": "z", "value": 1},
            {"a": "a", "b": "c", "value": 1},
            {"a": "b", "b": "c", "value": 1},
        ])
        with pytest.raises(ValueError, match="z"):
            build_comparison_matrix(config)


class TestComputeAhpWeights:
    def test_all_equal_comparisons_give_equal_weights(self):
        matrix, _ = build_comparison_matrix(_toy_config())
        weights = compute_ahp_weights(matrix)
        assert weights == pytest.approx([1 / 3, 1 / 3, 1 / 3], abs=1e-9)

    def test_weights_sum_to_one(self):
        config = _toy_config(comparisons=[
            {"a": "a", "b": "b", "value": 5},
            {"a": "a", "b": "c", "value": 7},
            {"a": "b", "b": "c", "value": 3},
        ])
        matrix, _ = build_comparison_matrix(config)
        weights = compute_ahp_weights(matrix)
        assert weights.sum() == pytest.approx(1.0)

    def test_stronger_preference_gives_higher_weight(self):
        # a is judged strongly more important than both b and c.
        config = _toy_config(comparisons=[
            {"a": "a", "b": "b", "value": 8},
            {"a": "a", "b": "c", "value": 8},
            {"a": "b", "b": "c", "value": 1},
        ])
        matrix, criteria = build_comparison_matrix(config)
        weights = compute_ahp_weights(matrix)
        weight_map = dict(zip(criteria, weights))
        assert weight_map["a"] > weight_map["b"]
        assert weight_map["a"] > weight_map["c"]


class TestComputeConsistencyRatio:
    def test_perfectly_consistent_matrix_has_zero_consistency_ratio(self):
        # All-equal comparisons: lambda_max == n exactly.
        matrix, _ = build_comparison_matrix(_toy_config())
        weights = compute_ahp_weights(matrix)
        result = compute_consistency_ratio(matrix, weights)
        assert result["consistency_ratio"] == pytest.approx(0.0, abs=1e-9)
        assert result["is_consistent"] is True

    def test_transitively_consistent_matrix_stays_under_threshold(self):
        # a > b (2x), b > c (2x), so a > c should be ~4x for consistency.
        config = _toy_config(comparisons=[
            {"a": "a", "b": "b", "value": 2},
            {"a": "a", "b": "c", "value": 4},
            {"a": "b", "b": "c", "value": 2},
        ])
        matrix, _ = build_comparison_matrix(config)
        weights = compute_ahp_weights(matrix)
        result = compute_consistency_ratio(matrix, weights)
        assert result["is_consistent"] is True

    def test_contradictory_judgments_are_flagged_inconsistent(self):
        # a >> b, b >> c, but then c >> a -- a genuine logical contradiction
        # (if a > b and b > c, a should not be judged less important than c).
        config = _toy_config(comparisons=[
            {"a": "a", "b": "b", "value": 9},
            {"a": "b", "b": "c", "value": 9},
            {"a": "a", "b": "c", "value": 1 / 9},
        ])
        matrix, _ = build_comparison_matrix(config)
        weights = compute_ahp_weights(matrix)
        result = compute_consistency_ratio(matrix, weights)
        assert result["is_consistent"] is False
        assert result["consistency_ratio"] > 0.10


class TestDeriveWeightsFromConfig:
    def test_real_project_config_is_internally_consistent(self):
        """The actual config/ahp_pairwise_comparisons.yaml judgments used for
        this project's own risk_score criteria must pass Saaty's consistency
        check -- otherwise the judgments themselves are self-contradictory
        and the derived weights can't be trusted."""
        result = derive_weights_from_config(str(REAL_CONFIG_PATH))
        assert result["is_consistent"] is True
        assert result["consistency_ratio"] < 0.10

    def test_real_project_config_weights_sum_to_one(self):
        result = derive_weights_from_config(str(REAL_CONFIG_PATH))
        assert sum(result["weights"].values()) == pytest.approx(1.0)

    def test_real_project_config_covers_all_scoring_criteria(self):
        from score_suppliers import REQUIRED_WEIGHT_KEYS
        result = derive_weights_from_config(str(REAL_CONFIG_PATH))
        assert set(result["weights"].keys()) == set(REQUIRED_WEIGHT_KEYS)
