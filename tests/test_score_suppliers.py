# -*- coding: utf-8 -*-
"""Tests for the risk-scoring engine, focused on the HHI-inspired
concentration-risk logic (docs/research_v2.md section 3.1) added in v2."""

import pandas as pd
import pytest

from score_suppliers import compute_portfolio_hhi, compute_risk_score


class TestComputePortfolioHHI:
    def test_perfectly_even_split_gives_expected_hhi(self):
        # 4 suppliers at 25% each: HHI = 4 * 0.25^2 * 10,000 = 2,500
        shares = pd.Series([0.25, 0.25, 0.25, 0.25])
        assert compute_portfolio_hhi(shares) == pytest.approx(2500.0)

    def test_single_supplier_monopoly_gives_max_hhi(self):
        shares = pd.Series([1.0])
        assert compute_portfolio_hhi(shares) == pytest.approx(10_000.0)

    def test_more_even_spread_is_lower_than_concentrated_spread(self):
        even = pd.Series([0.1] * 10)  # 10 suppliers at 10% each
        concentrated = pd.Series([0.5, 0.5 / 9] * 1 + [0.5 / 9] * 8)  # one dominant supplier
        assert compute_portfolio_hhi(even) < compute_portfolio_hhi(concentrated)


class TestDependencyRiskUsesSquaredShare:
    """The whole point of the HHI-inspired change: a supplier with a much
    higher share should be penalized *disproportionately* more than a
    linear ratio would, once normalized onto the same 0-100 scale."""

    def _toy_config(self):
        return {
            "weights": {
                "delivery_delay_rate": 0.25,
                "price_volatility": 0.25,
                "supplier_dependency_ratio": 0.25,
                "quality_return_rate": 0.25,
            },
            "risk_level_thresholds": {"low_percentile": 0.34, "high_percentile": 0.67},
        }

    def test_high_share_supplier_scores_disproportionately_higher(self):
        # Three suppliers with dependency ratios 0.02, 0.06, 0.30 — all other
        # metrics held identical so only supplier_dependency_ratio_score can
        # explain any difference in risk_score.
        df = pd.DataFrame({
            "delivery_delay_rate": [0.1, 0.1, 0.1],
            "price_volatility": [0.1, 0.1, 0.1],
            "supplier_dependency_ratio": [0.02, 0.06, 0.30],
            "quality_return_rate": [0.1, 0.1, 0.1],
        })
        scored = compute_risk_score(df, self._toy_config())

        # Linear normalization of [0.02, 0.06, 0.30] would place the middle
        # supplier at (0.06-0.02)/(0.30-0.02)=14.3 on a 0-100 scale. Squaring
        # first compresses it much lower, since 0.06^2 is tiny relative to
        # 0.30^2's dominance of the range.
        linear_normalized_middle = (0.06 - 0.02) / (0.30 - 0.02) * 100
        assert scored.loc[1, "supplier_dependency_ratio_score"] < linear_normalized_middle

    def test_dependency_ratio_column_itself_stays_linear_not_squared(self):
        # The displayed/raw ratio must remain human-readable (e.g. "12%"),
        # even though the score derived from it uses the squared value.
        df = pd.DataFrame({
            "delivery_delay_rate": [0.1, 0.1],
            "price_volatility": [0.1, 0.1],
            "supplier_dependency_ratio": [0.02, 0.30],
            "quality_return_rate": [0.1, 0.1],
        })
        scored = compute_risk_score(df, self._toy_config())
        assert scored.loc[0, "supplier_dependency_ratio"] == pytest.approx(0.02)
        assert scored.loc[1, "supplier_dependency_ratio"] == pytest.approx(0.30)
