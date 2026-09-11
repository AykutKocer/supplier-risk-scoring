# -*- coding: utf-8 -*-
"""Tests for the Turkish-context due-diligence red flags added to the
synthetic generator (docs/research_v2.md section 4.3): has_export_documentation,
requires_full_upfront_payment, site_visit_verified."""

import random

import pandas as pd
import pytest

from generate_suppliers import generate_clean_supplier
from cleaning import SourceProfile, clean_with_profile

RED_FLAG_COLUMNS = [
    "has_export_documentation",
    "requires_full_upfront_payment",
    "site_visit_verified",
]


def _generate_many(n=4000, seed=42):
    random.seed(seed)
    rows = [generate_clean_supplier(i) for i in range(n)]
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def suppliers():
    return _generate_many()


class TestRedFlagGeneration:
    """These are binary presence/absence flags a due-diligence checklist
    would record, size-tiered the same way as the other risk signals: smaller,
    less established suppliers are more likely to trip a red flag."""

    def test_all_three_columns_are_present_and_boolean(self, suppliers):
        for col in RED_FLAG_COLUMNS:
            assert col in suppliers.columns
            assert set(suppliers[col].unique()) <= {True, False}

    def test_micro_suppliers_less_often_have_export_documentation(self, suppliers):
        rate_by_size = suppliers.groupby("company_size")["has_export_documentation"].mean()
        assert rate_by_size["Mikro"] < rate_by_size["Buyuk"]

    def test_micro_suppliers_more_often_require_full_upfront_payment(self, suppliers):
        rate_by_size = suppliers.groupby("company_size")["requires_full_upfront_payment"].mean()
        assert rate_by_size["Mikro"] > rate_by_size["Buyuk"]

    def test_micro_suppliers_less_often_have_a_verified_site_visit(self, suppliers):
        rate_by_size = suppliers.groupby("company_size")["site_visit_verified"].mean()
        assert rate_by_size["Mikro"] < rate_by_size["Buyuk"]


# --- Cleaning: boolean category maps for the new columns --------------------

TOY_BOOLEAN_PROFILE = SourceProfile.model_validate({
    "name": "toy_boolean_profile",
    "description": "Minimal profile isolating the evet/hayir -> True/False category map pattern used for the red-flag columns.",
    "required_canonical_columns": RED_FLAG_COLUMNS,
    "category_maps": [
        {
            "canonical_name": col,
            "value_map": {
                "evet": True, "yes": True, "1": True, "true": True,
                "hayir": False, "no": False, "0": False, "false": False,
            },
        }
        for col in RED_FLAG_COLUMNS
    ],
})


def test_turkish_yes_no_values_clean_to_booleans():
    df = pd.DataFrame({
        "has_export_documentation": ["Evet", "HAYIR"],
        "requires_full_upfront_payment": ["hayir", "evet"],
        "site_visit_verified": ["1", "0"],
    })
    result = clean_with_profile(df, TOY_BOOLEAN_PROFILE)
    assert list(result["has_export_documentation"]) == [True, False]
    assert list(result["requires_full_upfront_payment"]) == [False, True]
    assert list(result["site_visit_verified"]) == [True, False]
