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


def compute_risk_score(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    df = df.copy()
    weights = config["weights"]
    thresholds = config["risk_level_thresholds"]

    for metric in REQUIRED_WEIGHT_KEYS:
        df[f"{metric}_score"] = minmax_normalize_to_100(df[metric])

    df["risk_score"] = sum(
        df[f"{metric}_score"] * weight for metric, weight in weights.items()
    ).round(1)

    # Percentile-based cutoffs (see config comments for why): label a
    # supplier relative to the rest of the current population rather than
    # against a fixed absolute score.
    low_cutoff = df["risk_score"].quantile(thresholds["low_percentile"])
    high_cutoff = df["risk_score"].quantile(thresholds["high_percentile"])
    df["risk_level"] = pd.cut(
        df["risk_score"],
        bins=[-np.inf, low_cutoff, high_cutoff, np.inf],
        labels=["Low", "Medium", "High"],
    )
    return df


def main():
    config = load_config(CONFIG_PATH)
    df = pd.read_csv(INPUT_PATH, encoding="utf-8-sig")

    df = compute_metrics(df)
    df = compute_risk_score(df, config)

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
    )
    result = df[output_columns].sort_values("risk_score", ascending=False)
    result.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print(f"Scored {len(result)} suppliers -> {OUTPUT_PATH}")
    print()
    print("Risk level distribution:")
    print(result["risk_level"].value_counts())
    print()
    print(f"Suppliers with at least one estimated (imputed) input: {result['has_estimated_inputs'].sum()}")
    print()
    print("Top 5 highest-risk suppliers:")
    print(result[["company_name", "sector", "risk_score", "risk_level"]].head(5).to_string(index=False))


if __name__ == "__main__":
    main()
