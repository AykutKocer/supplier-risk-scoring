# -*- coding: utf-8 -*-
"""Tests for the risk-scoring engine, focused on the HHI-inspired
concentration-risk logic (docs/research_v2.md section 3.1) added in v2."""

import pandas as pd
import pytest

from score_suppliers import (
    assign_risk_level,
    compute_cbam_compliance_risk,
    compute_portfolio_hhi,
    compute_risk_score,
    compute_sector_hhi,
)


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


class TestAssignRiskLevel:
    """assign_risk_level must never crash, even on the degenerate inputs
    (tiny populations, many tied scores) where the percentile cutoffs
    collapse onto the same value — a real bug found while testing
    financial_risk_score against a 3-row toy DataFrame (plain pd.cut raises
    on duplicate bin edges in that case)."""

    THRESHOLDS = {"low_percentile": 0.34, "high_percentile": 0.67}

    def test_normal_case_produces_all_three_labels(self):
        scores = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0])
        levels = assign_risk_level(scores, self.THRESHOLDS)
        assert set(levels.astype(str)) == {"Low", "Medium", "High"}

    def test_all_identical_scores_does_not_raise(self):
        scores = pd.Series([50.0, 50.0, 50.0])
        levels = assign_risk_level(scores, self.THRESHOLDS)
        assert not levels.isna().any()

    def test_mostly_zero_with_one_outlier_does_not_raise(self):
        # The exact shape that broke plain pd.cut: low_cutoff == high_cutoff == 0.0
        scores = pd.Series([0.0, 0.0, 75.0])
        levels = assign_risk_level(scores, self.THRESHOLDS)
        assert levels.iloc[2] == "High"
        assert not levels.isna().any()


class TestComputeSectorHhi:
    """Per-sector concentration risk (docs/research_v2.md roadmap): a
    supplier dominant within a small sector can be invisible to
    portfolio-wide HHI, which is exactly the v1 README's documented
    limitation this closes."""

    def _toy_df(self):
        return pd.DataFrame({
            "sector": ["A", "A", "A", "A", "B", "B"],
            "annual_purchase_volume_tl": [25, 25, 25, 25, 90, 10],
        })

    def test_returns_one_row_per_sector(self):
        result = compute_sector_hhi(self._toy_df())
        assert set(result["sector"]) == {"A", "B"}
        assert len(result) == 2

    def test_evenly_split_sector_has_lower_hhi_than_concentrated_sector(self):
        result = compute_sector_hhi(self._toy_df()).set_index("sector")
        # Sector A: 4 suppliers at 25% each -> HHI = 4 * 0.25^2 * 10,000 = 2,500
        # Sector B: 90%/10% split -> HHI = (0.9^2 + 0.1^2) * 10,000 = 8,200
        assert result.loc["A", "sector_hhi"] == pytest.approx(2500.0)
        assert result.loc["B", "sector_hhi"] == pytest.approx(8200.0)
        assert result.loc["B", "sector_hhi"] > result.loc["A", "sector_hhi"]

    def test_sorted_most_concentrated_first(self):
        result = compute_sector_hhi(self._toy_df())
        assert result.iloc[0]["sector"] == "B"

    def test_concentration_level_uses_doj_style_thresholds(self):
        result = compute_sector_hhi(self._toy_df()).set_index("sector")
        assert result.loc["A", "concentration_level"] == "Moderate"  # 2,500 exactly -> the moderate/high boundary itself
        assert result.loc["B", "concentration_level"] == "High"

    def test_supplier_count_and_total_volume_are_reported(self):
        result = compute_sector_hhi(self._toy_df()).set_index("sector")
        assert result.loc["A", "supplier_count"] == 4
        assert result.loc["A", "total_purchase_volume_tl"] == pytest.approx(100.0)
        assert result.loc["B", "supplier_count"] == 2
        assert result.loc["B", "total_purchase_volume_tl"] == pytest.approx(100.0)

    def test_a_sector_dominated_by_a_single_supplier_hits_the_max(self):
        df = pd.DataFrame({"sector": ["A", "A", "A"], "annual_purchase_volume_tl": [100, 0, 0]})
        result = compute_sector_hhi(df).set_index("sector")
        assert result.loc["A", "sector_hhi"] == pytest.approx(10_000.0)


class TestComputeCbamComplianceRisk:
    """CBAM/CSRD compliance exposure (docs/research_v2.md section 4.2): a
    boolean applicability + gap check, not a continuous score -- flags
    suppliers in a CBAM-covered sector, selling into the EU, without the
    emissions-reporting capability CBAM/CSRD actually requires."""

    CBAM_SECTORS = ["Metal ve Çelik"]

    def _toy_df(self, **overrides):
        base = {
            "sector": ["Metal ve Çelik"],
            "exports_to_eu": [True],
            "has_emissions_reporting_capability": [False],
        }
        base.update(overrides)
        return pd.DataFrame(base)

    def test_flags_the_exact_triple_condition(self):
        df = self._toy_df()
        result = compute_cbam_compliance_risk(df, self.CBAM_SECTORS)
        assert result.iloc[0] == True  # noqa: E712

    def test_not_flagged_when_sector_out_of_scope(self):
        df = self._toy_df(sector=["Tekstil"])
        result = compute_cbam_compliance_risk(df, self.CBAM_SECTORS)
        assert result.iloc[0] == False  # noqa: E712

    def test_not_flagged_when_not_exporting_to_eu(self):
        df = self._toy_df(exports_to_eu=[False])
        result = compute_cbam_compliance_risk(df, self.CBAM_SECTORS)
        assert result.iloc[0] == False  # noqa: E712

    def test_not_flagged_when_reporting_capability_exists(self):
        df = self._toy_df(has_emissions_reporting_capability=[True])
        result = compute_cbam_compliance_risk(df, self.CBAM_SECTORS)
        assert result.iloc[0] == False  # noqa: E712

    def test_missing_exports_to_eu_treated_as_false_not_flagged(self):
        df = self._toy_df(exports_to_eu=[None])
        result = compute_cbam_compliance_risk(df, self.CBAM_SECTORS)
        assert result.iloc[0] == False  # noqa: E712

    def test_missing_reporting_capability_treated_as_false_and_flagged(self):
        # Missing data on whether a supplier has reporting capability is
        # itself the gap this flag exists to surface, not a reason to skip it.
        df = self._toy_df(has_emissions_reporting_capability=[None])
        result = compute_cbam_compliance_risk(df, self.CBAM_SECTORS)
        assert result.iloc[0] == True  # noqa: E712

    def test_multiple_rows_evaluated_independently(self):
        df = pd.DataFrame({
            "sector": ["Metal ve Çelik", "Metal ve Çelik", "Tekstil"],
            "exports_to_eu": [True, False, True],
            "has_emissions_reporting_capability": [False, False, False],
        })
        result = compute_cbam_compliance_risk(df, self.CBAM_SECTORS)
        assert result.tolist() == [True, False, False]
