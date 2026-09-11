# -*- coding: utf-8 -*-
"""
Generates a multi-period (quarterly) supplier history: the same 85
suppliers re-assessed across four quarters, with performance and financial
metrics drifting period to period via a bounded random walk -- not
independently re-randomized each quarter.

Why this exists: a single point-in-time snapshot can't show risk *trend*.
docs/research_v2.md section 2.2 documents this as a real, cited gap in how
supplier risk is actually managed in practice -- "tiers rarely get
revisited after onboarding", and a supplier can move from low to high risk
within weeks with nothing to catch it. This generator produces synthetic
evidence of exactly that kind of drift so src/risk_trend.py has real
period-to-period data to detect it in.

Supplier identity fields (name, sector, city, size tier, VKN, founding
year, ISO certification) stay fixed across periods -- only the fields a
periodic reassessment would actually re-measure drift. Dates
(contract_start_date, last_audit_date) also stay fixed for simplicity; a
real deployment would update last_audit_date when a new audit occurs, but
that's not this feature's point.

Reuses generate_suppliers.py's own record generator and messiness injector
rather than duplicating them, so this history dataset is messy in exactly
the same way the main dataset is and cleans through the same
config/erp_profiles/synthetic_generator.yaml profile unchanged (the
profile-driven engine passes the extra `period` column through untouched --
see src/cleaning/engine.py's "unmapped columns pass through" behavior).
"""

import random
import sys

import pandas as pd

sys.path.append(".")
sys.path.append("src")
from generate_suppliers import RANDOM_SEED, N_SUPPLIERS, generate_clean_supplier, messify

PERIODS = ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"]
OUTPUT_PATH = "data/raw/suppliers_history_raw.csv"


def _drift_ratio(value: float, rng: random.Random, spread: float, low: float = 0.0, high: float = None) -> float:
    """Nudges `value` by a random +-spread fraction (a bounded random walk,
    not an independent re-roll), clipped to [low, high]."""
    result = value * (1 + rng.uniform(-spread, spread))
    result = max(low, result)
    if high is not None:
        result = min(high, result)
    return result


def drift_record(prev: dict, rng: random.Random) -> dict:
    """Produces the next quarter's record from the previous quarter's,
    drifting only the fields a periodic reassessment would actually
    re-measure."""
    nxt = dict(prev)

    total_orders = max(1, round(_drift_ratio(prev["total_orders_last_year"], rng, spread=0.10)))
    late_orders = min(total_orders, max(0, round(_drift_ratio(prev["late_orders_last_year"], rng, spread=0.25))))
    nxt["total_orders_last_year"] = total_orders
    nxt["late_orders_last_year"] = late_orders

    for q in ["price_q1", "price_q2", "price_q3", "price_q4"]:
        nxt[q] = round(_drift_ratio(prev[q], rng, spread=0.08), 2)

    units_shipped = max(1, round(_drift_ratio(prev["units_shipped_last_year"], rng, spread=0.10)))
    units_returned = min(units_shipped, max(0, round(_drift_ratio(prev["units_returned_last_year"], rng, spread=0.25))))
    nxt["units_shipped_last_year"] = units_shipped
    nxt["units_returned_last_year"] = units_returned

    nxt["annual_purchase_volume_tl"] = round(_drift_ratio(prev["annual_purchase_volume_tl"], rng, spread=0.10), 2)

    nxt["overdue_debt_ratio"] = round(_drift_ratio(prev["overdue_debt_ratio"], rng, spread=0.30, low=0.0, high=0.95), 4)
    nxt["debt_to_revenue_ratio"] = round(_drift_ratio(prev["debt_to_revenue_ratio"], rng, spread=0.30, low=0.0, high=3.0), 4)

    # A payment default in the trailing-3-year window is sticky once true
    # (matches how a real "last 3 years" flag behaves) but can newly appear
    # with a small per-quarter probability.
    if not prev["payment_default_last_3y"] and rng.random() < 0.03:
        nxt["payment_default_last_3y"] = True

    for flag in ["has_export_documentation", "site_visit_verified", "requires_full_upfront_payment"]:
        if rng.random() < 0.05:
            nxt[flag] = not prev[flag]

    return nxt


def generate_history() -> pd.DataFrame:
    rng = random.Random(RANDOM_SEED)
    current = [generate_clean_supplier(i + 1) for i in range(N_SUPPLIERS)]

    rows = []
    for period in PERIODS:
        for record in current:
            row = dict(record)
            row["period"] = period
            rows.append(row)
        current = [drift_record(record, rng) for record in current]

    return pd.DataFrame(rows)


def main():
    history_df = generate_history()
    messy_df = messify(history_df)
    messy_df = messy_df.sample(frac=1, random_state=RANDOM_SEED).reset_index(drop=True)
    messy_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    print(f"Generated {len(messy_df)} supplier-period rows "
          f"({N_SUPPLIERS} suppliers x {len(PERIODS)} periods) -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
