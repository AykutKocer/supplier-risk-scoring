# -*- coding: utf-8 -*-
"""
Compute a 0-100 supplier risk score and a Low/Medium/High label from the
cleaned supplier dataset.

Method (a standard weighted-scorecard / multi-criteria approach):
  1. Compute four raw business metrics per supplier.
  2. Min-max normalize each metric across all suppliers onto a 0-100 "risk
     contribution" scale (the highest-risk supplier on that single metric
     scores 100, the lowest scores 0). This step is necessary because the
     four raw metrics live on completely different scales (a rate between
     0-1 vs. a TL amount in the millions) and can't be combined directly.
  3. Combine the four normalized scores using the weights in
     config/scoring_weights.yaml to get the final risk_score.
  4. Map risk_score to a Low/Medium/High label using the thresholds in the
     same config file.

Missing raw inputs (see data/processed/suppliers_clean.csv) are imputed with
the column median before computing metrics, and every supplier that required
imputation is flagged in `has_estimated_inputs` so this is never silently
hidden from downstream analysis.
"""

import sys

import numpy as np
import pandas as pd
import yaml

# Windows consoles often use a legacy codepage that can't print every
# Turkish/Unicode character; force UTF-8 output so a print never crashes.
# (Guarded because Jupyter's stdout replacement doesn't support reconfigure,
# and doesn't need it — it already handles Unicode natively.)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

INPUT_PATH = "data/processed/suppliers_clean.csv"
CONFIG_PATH = "config/scoring_weights.yaml"
OUTPUT_PATH = "reports/supplier_risk_scores.csv"

REQUIRED_WEIGHT_KEYS = [
    "delivery_delay_rate",
    "price_volatility",
    "supplier_dependency_ratio",
    "quality_return_rate",
]


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    weights = config["weights"]
    missing_keys = set(REQUIRED_WEIGHT_KEYS) - set(weights)
    if missing_keys:
        raise ValueError(f"Missing weight(s) in {path}: {missing_keys}")
    total = sum(weights.values())
    if not np.isclose(total, 1.0, atol=0.001):
        raise ValueError(f"Weights in {path} must sum to 1.0, got {total:.3f}")

    return config


def impute_median(df: pd.DataFrame, columns: list) -> pd.Series:
    """Fills missing values in the given columns with the column median and
    returns a boolean Series marking every row that needed any imputation."""
    was_missing = df[columns].isna().any(axis=1)
    for col in columns:
        df[col] = df[col].fillna(df[col].median())
    return was_missing


def minmax_normalize_to_100(series: pd.Series) -> pd.Series:
    """Scales a metric so the riskiest supplier (highest raw value) scores
    100 and the safest (lowest raw value) scores 0."""
    min_val, max_val = series.min(), series.max()
    if np.isclose(max_val, min_val):
        # Every supplier has the same value on this metric: no basis to rank
        # them against each other, so nobody is flagged as riskier.
        return pd.Series(0.0, index=series.index)
    return (series - min_val) / (max_val - min_val) * 100


def assign_risk_level(score: pd.Series, thresholds: dict) -> pd.Series:
    """Labels a 0-100 score Low/Medium/High by percentile within the given
    population (see config/scoring_weights.yaml comments for why percentile,
    not a fixed cutoff). Falls back to a Low/High-only split if the low and
    high cutoffs land on the same value — degenerate with a very small or
    very tied population, but a real edge case a robust function shouldn't
    just crash on (pd.cut errors on duplicate bin edges)."""
    low_cutoff = score.quantile(thresholds["low_percentile"])
    high_cutoff = score.quantile(thresholds["high_percentile"])
    if np.isclose(low_cutoff, high_cutoff):
        labels = np.where(score > low_cutoff, "High", "Low")
        return pd.Series(labels, index=score.index, dtype=pd.CategoricalDtype(["Low", "Medium", "High"], ordered=True))
    return pd.cut(score, bins=[-np.inf, low_cutoff, high_cutoff, np.inf], labels=["Low", "Medium", "High"])


def compute_metrics(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    flags = []
    flags.append(impute_median(df, ["late_orders_last_year", "total_orders_last_year"]))
    df["delivery_delay_rate"] = df["late_orders_last_year"] / df["total_orders_last_year"]

    price_cols = ["price_q1", "price_q2", "price_q3", "price_q4"]
    flags.append(df[price_cols].isna().any(axis=1))
    price_mean = df[price_cols].mean(axis=1, skipna=True)
    price_std = df[price_cols].std(axis=1, skipna=True)
    df["price_volatility"] = price_std / price_mean
    df["price_volatility"] = df["price_volatility"].fillna(df["price_volatility"].median())

    flags.append(impute_median(df, ["annual_purchase_volume_tl"]))
    total_volume = df["annual_purchase_volume_tl"].sum()
    df["supplier_dependency_ratio"] = df["annual_purchase_volume_tl"] / total_volume

    flags.append(impute_median(df, ["units_returned_last_year", "units_shipped_last_year"]))
    df["quality_return_rate"] = df["units_returned_last_year"] / df["units_shipped_last_year"]

    df["has_estimated_inputs"] = np.logical_or.reduce(flags)
    return df


def compute_portfolio_hhi(dependency_ratios: pd.Series) -> float:
    """Herfindahl-Hirschman Index of the whole supplier portfolio: the sum of
    each supplier's squared share of total spend, scaled to the conventional
    0-10,000 range. A real, standard economics concentration metric (used by
    the US DOJ for antitrust review) — not invented for this project. DOJ
    reference thresholds, also used in procurement concentration-risk
    contexts: <1,500 = low concentration, 1,500-2,500 = moderate, >2,500 =
    high. See docs/research_v2.md section 3.1."""
    return float((dependency_ratios ** 2).sum() * 10_000)


def compute_financial_risk_score(df: pd.DataFrame, thresholds: dict) -> pd.DataFrame:
    """Computes a separate 0-100 financial_risk_score (higher = riskier),
    deliberately NOT blended into risk_score.

    Financial/solvency risk ("will this company survive and pay its debts")
    and operational/performance risk ("does this company deliver well as a
    supplier") are genuinely different risk *types* — a supplier can be
    financially fragile but operationally excellent, or vice versa, and
    merging both into one number hides which kind of risk is actually
    driving a High rating. Real commercial platforms (e.g. SAP Ariba) keep
    financial, compliance, and sustainability risk as separate facets for
    the same reason — see docs/research_v2.md section 6. Keeping this axis
    separate also means it can be added without touching the existing,
    already-documented risk_score weights in config/scoring_weights.yaml.

    Conceptually inspired by what a real Findeks Ticari Risk Raporu covers
    (payment habits, overdue debt, leverage) — NOT a reproduction of KKB's
    actual proprietary scoring formula, which isn't publicly published; see
    generate_suppliers.py's financial-field generation comment.
    """
    df = df.copy()

    was_missing = impute_median(df, ["overdue_debt_ratio", "debt_to_revenue_ratio"])
    df["payment_default_last_3y"] = df["payment_default_last_3y"].fillna(False)

    overdue_score = minmax_normalize_to_100(df["overdue_debt_ratio"])
    leverage_score = minmax_normalize_to_100(df["debt_to_revenue_ratio"])
    default_score = df["payment_default_last_3y"].astype(float) * 100.0

    df["financial_risk_score"] = (
        0.30 * overdue_score + 0.30 * leverage_score + 0.40 * default_score
    ).round(1)
    df["financial_risk_has_estimated_inputs"] = was_missing

    # Same percentile-based-labeling policy as the operational risk_score
    # (see compute_risk_score / config comments), applied to this separate
    # axis independently — reuses the same low/high_percentile config
    # values as a general "how to bucket a 0-100 risk score" policy, not
    # something specific to the four operational criteria.
    df["financial_risk_level"] = assign_risk_level(df["financial_risk_score"], thresholds)
    return df


def compute_risk_score(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    df = df.copy()
    weights = config["weights"]
    thresholds = config["risk_level_thresholds"]

    for metric in REQUIRED_WEIGHT_KEYS:
        if metric == "supplier_dependency_ratio":
            # HHI-inspired: normalize on each supplier's *squared* share, not
            # the linear share, so concentration risk grows non-linearly —
            # a supplier at 20% of spend is a much bigger single point of
            # failure than four suppliers at 5% each, and a linear ratio
            # can't tell those apart the way a squared share does (this is
            # exactly the logic behind the real HHI concentration index; see
            # compute_portfolio_hhi). The displayed `supplier_dependency_ratio`
            # column itself stays the plain, human-readable share — only the
            # score that feeds risk_score uses the squared version.
            df[f"{metric}_score"] = minmax_normalize_to_100(df[metric] ** 2)
        else:
            df[f"{metric}_score"] = minmax_normalize_to_100(df[metric])

    df["risk_score"] = sum(
        df[f"{metric}_score"] * weight for metric, weight in weights.items()
    ).round(1)

    # Percentile-based cutoffs (see config comments for why): label a
    # supplier relative to the rest of the current population rather than
    # against a fixed absolute score.
    df["risk_level"] = assign_risk_level(df["risk_score"], thresholds)
    return df


def main():
    config = load_config(CONFIG_PATH)
    df = pd.read_csv(INPUT_PATH, encoding="utf-8-sig")

    df = compute_metrics(df)
    df = compute_risk_score(df, config)
    df = compute_financial_risk_score(df, config["risk_level_thresholds"])

    rate_columns = [
        "delivery_delay_rate", "price_volatility",
        "supplier_dependency_ratio", "quality_return_rate",
    ]
    score_columns = [f"{c}_score" for c in rate_columns]
    df[rate_columns] = df[rate_columns].round(4)
    df[score_columns] = df[score_columns].round(1)

    output_columns = (
        ["supplier_id", "company_name", "sector", "city", "company_size"]
        + rate_columns + score_columns
        + ["risk_score", "risk_level", "has_estimated_inputs"]
        # Separate axis, deliberately not blended into risk_score — see
        # compute_financial_risk_score's docstring.
        + ["financial_risk_score", "financial_risk_level", "financial_risk_has_estimated_inputs"]
    )
    result = df[output_columns].sort_values("risk_score", ascending=False)
    result.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print(f"Scored {len(result)} suppliers -> {OUTPUT_PATH}")
    print()
    print("Risk level distribution (operational):")
    print(result["risk_level"].value_counts())
    print()
    print("Financial risk level distribution (separate axis):")
    print(result["financial_risk_level"].value_counts())
    print()
    print(f"Suppliers with at least one estimated (imputed) input: {result['has_estimated_inputs'].sum()}")
    print()
    portfolio_hhi = compute_portfolio_hhi(df["supplier_dependency_ratio"])
    hhi_level = "low" if portfolio_hhi < 1_500 else "moderate" if portfolio_hhi < 2_500 else "high"
    print(f"Portfolio concentration (HHI): {portfolio_hhi:.0f} / 10,000 ({hhi_level} concentration, "
          f"DOJ-style thresholds: <1,500 low, 1,500-2,500 moderate, >2,500 high)")
    print()
    print("Top 5 highest-risk suppliers (operational):")
    print(result[["company_name", "sector", "risk_score", "risk_level"]].head(5).to_string(index=False))
    print()
    print("Top 5 highest financial-risk suppliers:")
    print(result.sort_values("financial_risk_score", ascending=False)
          [["company_name", "sector", "financial_risk_score", "financial_risk_level"]].head(5).to_string(index=False))


if __name__ == "__main__":
    main()
