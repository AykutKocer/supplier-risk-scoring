# -*- coding: utf-8 -*-
"""
The generic cleaning engine: applies any `SourceProfile` to any raw
DataFrame. This is the "Strategy Pattern" piece — the engine itself has no
knowledge of any specific ERP or dataset; all of that lives in the profile.

Usage:
    profile = load_profile("config/erp_profiles/synthetic_generator.yaml")
    raw_df = pd.read_csv("data/raw/suppliers_raw.csv", encoding=profile.encoding)
    clean_df = clean_with_profile(raw_df, profile)
"""

import sys
from pathlib import Path

import pandas as pd
import yaml

from .profile import SourceProfile
from .text_utils import (
    map_category,
    parse_messy_date,
    parse_messy_number,
    restore_from_canonical_list,
    title_case_free_text,
)


def load_profile(path: str | Path) -> SourceProfile:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return SourceProfile.model_validate(raw)


def _parse_numeric_series(series: pd.Series, decimal_style: str) -> pd.Series:
    if decimal_style == "auto":
        return series.apply(parse_messy_number)
    if decimal_style == "turkish":
        # Force Turkish convention regardless of what's in the cell: '.' is
        # always a thousands separator, ',' is always the decimal point.
        def _turkish(v):
            if pd.isna(v):
                return v
            return float(str(v).strip().replace(".", "").replace(",", "."))
        return series.apply(_turkish)
    if decimal_style == "international":
        return pd.to_numeric(series, errors="coerce")
    raise ValueError(f"Unknown decimal_style: {decimal_style!r}")


def clean_with_profile(df: pd.DataFrame, profile: SourceProfile) -> pd.DataFrame:
    df = df.copy()

    # 1) Rename raw source columns to canonical names. Columns not covered
    #    by the mapping pass through unchanged (kept, not dropped) so a
    #    partial/incomplete profile doesn't silently lose data.
    rename_map = {m.source_name: m.canonical_name for m in profile.column_mapping}
    df = df.rename(columns=rename_map)

    # 2) Fail fast and clearly if this profile doesn't actually match the file.
    missing = [c for c in profile.required_canonical_columns if c not in df.columns]
    if missing:
        raise ValueError(
            f"Profile '{profile.name}' expected columns {missing} after applying "
            f"column_mapping, but they're not present. This usually means the wrong "
            f"profile was used for this file, or the source export changed shape."
        )

    # 3) Category label normalization (small, enumerated variant sets).
    for spec in profile.category_maps:
        if spec.canonical_name not in df.columns:
            continue
        df[spec.canonical_name] = df[spec.canonical_name].apply(
            lambda v: map_category(v, spec.value_map, spec.canonical_name, profile.name)
        )

    # 4) Closed-list free text (sector, city, ...): restore canonical spelling.
    for spec in profile.closed_list_columns:
        if spec.canonical_name not in df.columns:
            continue
        df[spec.canonical_name] = df[spec.canonical_name].apply(
            lambda v: restore_from_canonical_list(v, spec.canonical_values, spec.canonical_name, profile.name)
        )

    # 5) Open free text (company_name, ...): normalize casing/whitespace only.
    for spec in profile.free_text_title_case_columns:
        if spec.canonical_name not in df.columns:
            continue
        df[spec.canonical_name] = df[spec.canonical_name].apply(
            lambda v: title_case_free_text(v, spec.known_suffixes)
        )

    # 6) Numbers.
    for spec in profile.numeric_columns:
        if spec.canonical_name not in df.columns:
            continue
        parsed = _parse_numeric_series(df[spec.canonical_name], spec.decimal_style)
        df[spec.canonical_name] = parsed.astype("Int64") if spec.target_dtype == "Int64" else parsed

    # 7) Dates.
    for spec in profile.date_columns:
        if spec.canonical_name not in df.columns:
            continue
        df[spec.canonical_name] = df[spec.canonical_name].apply(
            lambda v: parse_messy_date(v, spec.formats)
        )

    return df
