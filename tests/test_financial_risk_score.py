# -*- coding: utf-8 -*-
"""Tests for the separate financial_risk_score axis (deliberately not
blended into risk_score — see compute_financial_risk_score's docstring for
why)."""

import pandas as pd
import pytest

from score_suppliers import compute_financial_risk_score

THRESHOLDS = {"low_percentile": 0.34, "high_percentile": 0.67}


def _toy_df(**overrides):
    base = {
        "overdue_debt_ratio": [0.05, 0.05, 0.05],
        "debt_to_revenue_ratio": [0.3, 0.3, 0.3],
        "payment_default_last_3y": [False, False, False],
    }
    base.update(overrides)
    return pd.DataFrame(base)


class TestComputeFinancialRiskScore:
    def test_a_recent_default_dominates_the_score(self):
        df = _toy_df(payment_default_last_3y=[False, True, False])
        result = compute_financial_risk_score(df, THRESHOLDS)
        # Same overdue/leverage inputs for all three -> the defaulted
        # supplier must score strictly higher purely from the default flag.
        assert result.loc[1, "financial_risk_score"] > result.loc[0, "financial_risk_score"]
        assert result.loc[1, "financial_risk_score"] > result.loc[2, "financial_risk_score"]

    def test_higher_overdue_debt_scores_higher(self):
        df = _toy_df(overdue_debt_ratio=[0.01, 0.01, 0.50])
        result = compute_financial_risk_score(df, THRESHOLDS)
        assert result.loc[2, "financial_risk_score"] > result.loc[0, "financial_risk_score"]

    def test_higher_leverage_scores_higher(self):
        df = _toy_df(debt_to_revenue_ratio=[0.1, 0.1, 2.5])
        result = compute_financial_risk_score(df, THRESHOLDS)
        assert result.loc[2, "financial_risk_score"] > result.loc[0, "financial_risk_score"]

    def test_missing_ratio_inputs_are_flagged_not_hidden(self):
        df = _toy_df(overdue_debt_ratio=[0.05, None, 0.05])
        result = compute_financial_risk_score(df, THRESHOLDS)
        assert result.loc[1, "financial_risk_has_estimated_inputs"] == True  # noqa: E712
        assert result.loc[0, "financial_risk_has_estimated_inputs"] == False  # noqa: E712
        # And imputation still produces a usable (non-NaN) score.
        assert pd.notna(result.loc[1, "financial_risk_score"])

    def test_missing_default_flag_defaults_to_no_default(self):
        df = _toy_df(payment_default_last_3y=[False, None, False])
        result = compute_financial_risk_score(df, THRESHOLDS)
        assert pd.notna(result.loc[1, "financial_risk_score"])

    def test_risk_level_labels_are_assigned(self):
        df = _toy_df(
            overdue_debt_ratio=[0.01, 0.10, 0.60],
            debt_to_revenue_ratio=[0.1, 0.5, 2.0],
            payment_default_last_3y=[False, False, True],
        )
        result = compute_financial_risk_score(df, THRESHOLDS)
        assert set(result["financial_risk_level"].astype(str)) <= {"Low", "Medium", "High"}
        # The clearly-worst row (high overdue, high leverage, a default) must not be labeled Low.
        assert result.loc[2, "financial_risk_level"] != "Low"
