# -*- coding: utf-8 -*-
"""Tests for multi-period risk scoring and migration detection
(docs/research_v2.md section 2.2: "scoring is point-in-time; risk isn't").
Covers src/risk_trend.py and the drift logic in
src/generate_supplier_history.py."""

import random

import pandas as pd
import pytest

from risk_trend import compute_score_history, detect_risk_migrations
from generate_supplier_history import drift_record

WEIGHTS_CONFIG = {
    "weights": {
        "delivery_delay_rate": 0.35, "price_volatility": 0.25,
        "supplier_dependency_ratio": 0.25, "quality_return_rate": 0.15,
    },
    "risk_level_thresholds": {"low_percentile": 0.60, "high_percentile": 0.85},
}


def _toy_history_df(n_suppliers=6, periods=("2025-Q1", "2025-Q2")):
    rows = []
    for period in periods:
        for i in range(n_suppliers):
            rows.append({
                "supplier_id": f"SUP{i:03d}",
                "company_name": f"Company {i}",
                "period": period,
                "late_orders_last_year": 5 + i,
                "total_orders_last_year": 100,
                "price_q1": 100.0, "price_q2": 100.0 + i, "price_q3": 100.0, "price_q4": 100.0,
                "annual_purchase_volume_tl": 1000.0 * (i + 1),
                "units_shipped_last_year": 1000,
                "units_returned_last_year": 10 + i,
                "overdue_debt_ratio": 0.05 + i * 0.01,
                "debt_to_revenue_ratio": 0.2,
                "payment_default_last_3y": False,
            })
    return pd.DataFrame(rows)


class TestComputeScoreHistory:
    def test_scores_every_period_independently(self):
        history_df = _toy_history_df()
        result = compute_score_history(history_df, WEIGHTS_CONFIG)
        assert set(result["period"].unique()) == {"2025-Q1", "2025-Q2"}
        assert len(result) == 12  # 6 suppliers x 2 periods

    def test_each_period_gets_its_own_risk_levels(self):
        history_df = _toy_history_df()
        result = compute_score_history(history_df, WEIGHTS_CONFIG)
        assert set(result["risk_level"].astype(str)) <= {"Low", "Medium", "High"}
        assert set(result["financial_risk_level"].astype(str)) <= {"Low", "Medium", "High"}

    def test_reuses_the_real_scoring_functions_not_a_reimplementation(self):
        # Same weights config on a single-period slice must match
        # score_suppliers.compute_risk_score's own output exactly.
        from score_suppliers import compute_metrics, compute_risk_score

        history_df = _toy_history_df(periods=("2025-Q1",))
        trend_result = compute_score_history(history_df, WEIGHTS_CONFIG)

        direct_metrics = compute_metrics(history_df.drop(columns=["period"]))
        direct_result = compute_risk_score(direct_metrics, WEIGHTS_CONFIG)

        assert trend_result["risk_score"].tolist() == direct_result["risk_score"].tolist()


class TestDetectRiskMigrations:
    def _toy_trend_df(self, levels_by_period: dict):
        """levels_by_period: {period: [level, level, ...]} for a fixed set
        of suppliers, one level per period in the same supplier order."""
        rows = []
        for period, levels in levels_by_period.items():
            for i, level in enumerate(levels):
                rows.append({"supplier_id": f"SUP{i:03d}", "company_name": f"Company {i}",
                             "period": period, "risk_level": level})
        return pd.DataFrame(rows)

    def test_worsening_transition_is_flagged(self):
        trend_df = self._toy_trend_df({
            "2025-Q1": ["Low"],
            "2025-Q2": ["High"],
        })
        migrations = detect_risk_migrations(trend_df, "risk_level")
        assert len(migrations) == 1
        assert migrations.iloc[0]["level_from"] == "Low"
        assert migrations.iloc[0]["level_to"] == "High"

    def test_improving_transition_is_not_flagged(self):
        trend_df = self._toy_trend_df({
            "2025-Q1": ["High"],
            "2025-Q2": ["Low"],
        })
        migrations = detect_risk_migrations(trend_df, "risk_level")
        assert len(migrations) == 0

    def test_unchanged_level_is_not_flagged(self):
        trend_df = self._toy_trend_df({
            "2025-Q1": ["Medium"],
            "2025-Q2": ["Medium"],
        })
        migrations = detect_risk_migrations(trend_df, "risk_level")
        assert len(migrations) == 0

    def test_flags_multiple_suppliers_independently(self):
        trend_df = self._toy_trend_df({
            "2025-Q1": ["Low", "Low", "High"],
            "2025-Q2": ["Medium", "Low", "Low"],  # supplier 0 worsens, 1 stable, 2 improves
        })
        migrations = detect_risk_migrations(trend_df, "risk_level")
        assert len(migrations) == 1
        assert migrations.iloc[0]["supplier_id"] == "SUP000"

    def test_multi_period_chain_flags_each_worsening_step(self):
        trend_df = self._toy_trend_df({
            "2025-Q1": ["Low"],
            "2025-Q2": ["Medium"],
            "2025-Q3": ["Medium"],
            "2025-Q4": ["High"],
        })
        migrations = detect_risk_migrations(trend_df, "risk_level")
        assert len(migrations) == 2
        assert migrations.iloc[0]["period_from"] == "2025-Q1"
        assert migrations.iloc[1]["period_from"] == "2025-Q3"

    def test_empty_trend_returns_empty_dataframe_with_expected_columns(self):
        trend_df = pd.DataFrame(columns=["supplier_id", "company_name", "period", "risk_level"])
        migrations = detect_risk_migrations(trend_df, "risk_level")
        assert len(migrations) == 0
        assert "period_from" in migrations.columns


class TestDriftRecord:
    """generate_supplier_history.py's period-to-period drift must be a
    bounded random walk (values stay close to the previous period), not an
    independent re-roll -- otherwise there'd be no real 'trend' to detect,
    just noise."""

    def _base_record(self):
        return {
            "total_orders_last_year": 100, "late_orders_last_year": 10,
            "price_q1": 100.0, "price_q2": 100.0, "price_q3": 100.0, "price_q4": 100.0,
            "units_shipped_last_year": 1000, "units_returned_last_year": 50,
            "annual_purchase_volume_tl": 500_000.0,
            "overdue_debt_ratio": 0.1, "debt_to_revenue_ratio": 0.3,
            "payment_default_last_3y": False,
            "has_export_documentation": True, "site_visit_verified": True,
            "requires_full_upfront_payment": False,
            "exports_to_eu": False, "has_emissions_reporting_capability": False,
        }

    def test_drifted_values_stay_within_a_bounded_range_of_the_original(self):
        rng = random.Random(0)
        prev = self._base_record()
        nxt = drift_record(prev, rng)
        # Bounded random walk: nothing should move more than ~40% in one step.
        assert 0.5 * prev["annual_purchase_volume_tl"] < nxt["annual_purchase_volume_tl"] < 1.5 * prev["annual_purchase_volume_tl"]
        assert 0.5 * prev["price_q1"] < nxt["price_q1"] < 1.5 * prev["price_q1"]

    def test_late_orders_never_exceeds_total_orders(self):
        rng = random.Random(1)
        prev = self._base_record()
        for _ in range(20):
            nxt = drift_record(prev, rng)
            assert nxt["late_orders_last_year"] <= nxt["total_orders_last_year"]
            prev = nxt

    def test_units_returned_never_exceeds_units_shipped(self):
        rng = random.Random(2)
        prev = self._base_record()
        for _ in range(20):
            nxt = drift_record(prev, rng)
            assert nxt["units_returned_last_year"] <= nxt["units_shipped_last_year"]
            prev = nxt

    def test_ratios_stay_within_valid_bounds_over_many_steps(self):
        rng = random.Random(3)
        prev = self._base_record()
        for _ in range(50):
            nxt = drift_record(prev, rng)
            assert 0.0 <= nxt["overdue_debt_ratio"] <= 0.95
            assert 0.0 <= nxt["debt_to_revenue_ratio"] <= 3.0
            prev = nxt

    def test_payment_default_is_sticky_once_true(self):
        rng = random.Random(4)
        prev = self._base_record()
        prev["payment_default_last_3y"] = True
        nxt = drift_record(prev, rng)
        assert nxt["payment_default_last_3y"] is True

    def test_supplier_identity_fields_are_untouched_by_drift(self):
        rng = random.Random(5)
        prev = self._base_record()
        prev["company_name"] = "Test Co."
        prev["sector"] = "Tekstil"
        nxt = drift_record(prev, rng)
        assert nxt["company_name"] == "Test Co."
        assert nxt["sector"] == "Tekstil"
