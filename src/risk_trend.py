# -*- coding: utf-8 -*-
"""
Scores a multi-period supplier history and detects risk *migrations* --
period-to-period transitions into a worse risk category.

Why this exists: src/score_suppliers.py produces a single point-in-time
snapshot. docs/research_v2.md section 2.2 documents a real, cited gap with
that approach: in practice "tiers rarely get revisited after onboarding",
and a supplier can move from low to high risk within weeks with nothing to
catch it. This module scores each period independently (reusing
score_suppliers.py's own functions, unmodified) and then flags exactly
those transitions -- the concrete payoff of tracking risk over time instead
of trusting one snapshot indefinitely.

Percentile-based risk levels are computed *within each period's own
population* (consistent with score_suppliers.py's existing point-in-time
design) rather than against a fixed historical baseline -- a supplier can
still migrate to High even if its raw score barely moved, if the rest of
the portfolio improved around it. This is a deliberate, documented choice,
not an oversight -- see compute_score_history()'s docstring.
"""

import sys

import pandas as pd

from score_suppliers import compute_financial_risk_score, compute_metrics, compute_risk_score

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

INPUT_PATH = "data/processed/suppliers_history_clean.csv"
CONFIG_PATH = "config/scoring_weights.yaml"
TREND_OUTPUT_PATH = "reports/supplier_risk_trend.csv"
MIGRATIONS_OUTPUT_PATH = "reports/risk_migrations.csv"

RISK_LEVEL_ORDER = {"Low": 0, "Medium": 1, "High": 2}


def compute_score_history(history_df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Scores each period in `history_df` independently, using the exact
    same compute_metrics/compute_risk_score/compute_financial_risk_score
    functions score_suppliers.py uses for a single snapshot -- proving this
    isn't a parallel scoring implementation that could drift out of sync
    with the point-in-time pipeline.

    Percentile cutoffs (Low/Medium/High) are recomputed fresh within each
    period's own population, exactly as a real periodic review would: "top
    15% of this quarter's suppliers" is a moving target, not a fixed score
    threshold fixed once and never revisited. One side effect worth being
    explicit about: a supplier's risk_score can stay flat while its
    risk_level still migrates, if the rest of the portfolio shifted around
    it -- that's a feature of relative, percentile-based risk labeling
    (see score_suppliers.py's own rationale for using percentiles at all),
    not a bug in this trend logic."""
    thresholds = config["risk_level_thresholds"]
    scored_periods = []
    for period, group in history_df.groupby("period", sort=True):
        metrics = compute_metrics(group.reset_index(drop=True))
        scored = compute_risk_score(metrics, config)
        scored = compute_financial_risk_score(scored, thresholds)
        scored_periods.append(scored)
    return pd.concat(scored_periods, ignore_index=True)


def detect_risk_migrations(trend_df: pd.DataFrame, level_column: str = "risk_level") -> pd.DataFrame:
    """Flags every supplier period-to-period transition where `level_column`
    moves to a strictly worse category (Low -> Medium, Medium -> High, or
    Low -> High in one step). Does not flag improvements or same-level
    periods -- those aren't the gap this exists to catch."""
    rows = []
    for supplier_id, group in trend_df.sort_values("period").groupby("supplier_id"):
        group = group.reset_index(drop=True)
        ranks = group[level_column].map(RISK_LEVEL_ORDER)
        for i in range(1, len(group)):
            prev_rank, cur_rank = ranks.iloc[i - 1], ranks.iloc[i]
            if pd.isna(prev_rank) or pd.isna(cur_rank) or cur_rank <= prev_rank:
                continue
            rows.append({
                "supplier_id": supplier_id,
                "company_name": group.loc[i, "company_name"],
                "period_from": group.loc[i - 1, "period"],
                "period_to": group.loc[i, "period"],
                "level_from": group.loc[i - 1, level_column],
                "level_to": group.loc[i, level_column],
            })
    columns = ["supplier_id", "company_name", "period_from", "period_to", "level_from", "level_to"]
    return pd.DataFrame(rows, columns=columns)


def main():
    from score_suppliers import load_config

    config = load_config(CONFIG_PATH)
    history_df = pd.read_csv(INPUT_PATH, encoding="utf-8-sig")

    trend_df = compute_score_history(history_df, config)
    trend_df.to_csv(TREND_OUTPUT_PATH, index=False, encoding="utf-8-sig")
    print(f"Scored {trend_df['period'].nunique()} periods x "
          f"{trend_df['supplier_id'].nunique()} suppliers -> {TREND_OUTPUT_PATH}")

    operational_migrations = detect_risk_migrations(trend_df, "risk_level")
    operational_migrations["axis"] = "operational"
    financial_migrations = detect_risk_migrations(trend_df, "financial_risk_level")
    financial_migrations["axis"] = "financial"
    all_migrations = pd.concat([operational_migrations, financial_migrations], ignore_index=True)
    all_migrations.to_csv(MIGRATIONS_OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print()
    print(f"Risk migrations (level got worse between consecutive periods) -> {MIGRATIONS_OUTPUT_PATH}")
    print(f"Operational: {len(operational_migrations)} migration(s) across "
          f"{operational_migrations['supplier_id'].nunique() if len(operational_migrations) else 0} supplier(s)")
    print(f"Financial:   {len(financial_migrations)} migration(s) across "
          f"{financial_migrations['supplier_id'].nunique() if len(financial_migrations) else 0} supplier(s)")
    if len(all_migrations):
        print()
        print("All migrations:")
        print(all_migrations[["company_name", "axis", "period_from", "period_to", "level_from", "level_to"]]
              .to_string(index=False))


if __name__ == "__main__":
    main()
