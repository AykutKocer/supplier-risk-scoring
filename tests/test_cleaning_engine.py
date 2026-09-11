# -*- coding: utf-8 -*-
"""Tests for the generic profile-driven cleaning engine itself, independent
of any specific project dataset — a self-contained toy profile exercises
every feature (column renaming, category maps, closed-list restoration,
free-text title casing, numeric parsing in both decimal conventions, date
parsing) so this suite doesn't depend on the real project data files."""

from pathlib import Path

import pandas as pd
import pytest

from cleaning import SourceProfile, clean_with_profile

TOY_PROFILE = SourceProfile.model_validate({
    "name": "toy_test_profile",
    "description": "A minimal profile exercising every engine feature, for unit testing.",
    "column_mapping": [
        {"source_name": "Firma Adi", "canonical_name": "company_name"},
        {"source_name": "Sehir", "canonical_name": "city"},
    ],
    "required_canonical_columns": ["company_name", "city", "size_label"],
    "category_maps": [
        {"canonical_name": "size_label", "value_map": {"kucuk": "Small", "buyuk": "Large"}},
    ],
    "closed_list_columns": [
        {"canonical_name": "city", "canonical_values": ["İstanbul", "Ankara"]},
    ],
    "free_text_title_case_columns": [
        {"canonical_name": "company_name", "known_suffixes": {"ltd.": "Ltd."}},
    ],
    "numeric_columns": [
        {"canonical_name": "price", "decimal_style": "turkish", "target_dtype": "float"},
        {"canonical_name": "order_count", "decimal_style": "international", "target_dtype": "Int64"},
    ],
    "date_columns": [
        {"canonical_name": "signed_on", "formats": ["%d.%m.%Y", "%Y-%m-%d"]},
    ],
})


def _toy_raw_df():
    return pd.DataFrame({
        "Firma Adi": ["akar metal ltd."],
        "Sehir": ["ISTANBUL"],
        "size_label": ["KUCUK"],
        "price": ["1.234,56"],
        "order_count": ["42"],
        "signed_on": ["15.03.2021"],
    })


def test_column_mapping_renames_source_columns():
    result = clean_with_profile(_toy_raw_df(), TOY_PROFILE)
    assert "company_name" in result.columns
    assert "Firma Adi" not in result.columns


def test_closed_list_restores_diacritics_and_case():
    result = clean_with_profile(_toy_raw_df(), TOY_PROFILE)
    assert result.loc[0, "city"] == "İstanbul"


def test_category_map_normalizes_to_canonical_label():
    result = clean_with_profile(_toy_raw_df(), TOY_PROFILE)
    assert result.loc[0, "size_label"] == "Small"


def test_free_text_title_case_preserves_suffix():
    result = clean_with_profile(_toy_raw_df(), TOY_PROFILE)
    assert result.loc[0, "company_name"] == "Akar Metal Ltd."


def test_turkish_decimal_style_parses_correctly():
    result = clean_with_profile(_toy_raw_df(), TOY_PROFILE)
    assert result.loc[0, "price"] == pytest.approx(1234.56)


def test_international_target_dtype_is_nullable_int():
    result = clean_with_profile(_toy_raw_df(), TOY_PROFILE)
    assert str(result["order_count"].dtype) == "Int64"
    assert result.loc[0, "order_count"] == 42


def test_date_column_parses_to_timestamp():
    result = clean_with_profile(_toy_raw_df(), TOY_PROFILE)
    assert result.loc[0, "signed_on"] == pd.Timestamp("2021-03-15")


def test_missing_required_column_raises_clear_error():
    df = _toy_raw_df().drop(columns=["size_label"])
    with pytest.raises(ValueError, match="size_label"):
        clean_with_profile(df, TOY_PROFILE)


def test_unmapped_columns_pass_through_unchanged():
    df = _toy_raw_df()
    df["extra_column"] = ["untouched"]
    result = clean_with_profile(df, TOY_PROFILE)
    assert result.loc[0, "extra_column"] == "untouched"


# --- Integration check against this project's real pipeline -----------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_CSV = PROJECT_ROOT / "data" / "raw" / "suppliers_raw.csv"
REFERENCE_CLEAN_CSV = PROJECT_ROOT / "data" / "processed" / "suppliers_clean.csv"
SYNTHETIC_PROFILE_PATH = PROJECT_ROOT / "config" / "erp_profiles" / "synthetic_generator.yaml"


@pytest.mark.skipif(
    not (RAW_CSV.exists() and REFERENCE_CLEAN_CSV.exists()),
    reason="requires data/raw and data/processed to already exist (run the pipeline scripts first)",
)
def test_engine_reproduces_reference_clean_output():
    """Regression check: the v2 profile-driven engine must produce output
    equivalent to the last known-good data/processed/suppliers_clean.csv,
    given the same raw input and the project's own synthetic_generator
    profile. Values are compared after a CSV round-trip (matching how the
    reference file itself was produced) so dtype-only differences (e.g.
    Int64 vs float64, which CSV can't distinguish) don't cause false
    failures — this is intentional; see the class docstring in engine.py."""
    from cleaning import clean_with_profile, load_profile

    profile = load_profile(SYNTHETIC_PROFILE_PATH)
    raw_df = pd.read_csv(RAW_CSV, encoding=profile.encoding)
    reference = pd.read_csv(REFERENCE_CLEAN_CSV, encoding="utf-8-sig")

    cleaned = clean_with_profile(raw_df, profile)
    roundtrip_path = PROJECT_ROOT / "tests" / "_tmp_roundtrip.csv"
    cleaned.to_csv(roundtrip_path, index=False, encoding="utf-8-sig")
    try:
        cleaned_roundtrip = pd.read_csv(roundtrip_path, encoding="utf-8-sig")
    finally:
        roundtrip_path.unlink(missing_ok=True)

    assert list(cleaned_roundtrip.columns) == list(reference.columns)
    for col in reference.columns:
        left_na = reference[col].isna()
        right_na = cleaned_roundtrip[col].isna()
        mismatch = (reference[col].astype(str) != cleaned_roundtrip[col].astype(str)) & ~(left_na & right_na)
        assert not mismatch.any(), f"Column '{col}' has {mismatch.sum()} mismatched row(s) vs the reference output"
