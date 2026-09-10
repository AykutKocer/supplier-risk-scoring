# -*- coding: utf-8 -*-
"""
Clean the raw synthetic supplier export and write a standardized version to
data/processed/.

Key cleaning problems solved here (see data/raw/suppliers_raw.csv):
- Mixed decimal separators (Turkish "1.234,56" vs plain "1234.56").
- Mixed date formats across rows.
- Inconsistent / bilingual category labels (company size, ISO certification).
- Casing noise, including cases where Python's locale-unaware str.upper()/
  str.lower() mangles Turkish ı/İ ("Turkish I problem") — handled by mapping
  Turkish letters to a plain-ASCII key BEFORE lowercasing, instead of relying
  on Python's built-in case folding.

Output category labels (company_size, and the risk level added later in the
scoring step) are standardized to ENGLISH, per project convention, even
though free-text fields like company_name stay in Turkish.

Missing values are NOT imputed here — they are left as proper NaN/NaT/pd.NA
so the scoring step can decide, per column, whether a missing value means
"unknown" (needs imputation) or "not applicable" (e.g. a supplier that has
never been audited).
"""

import sys
import unicodedata

import numpy as np
import pandas as pd

from generate_suppliers import SECTOR_NAMES, INDUSTRIAL_CITIES, OTHER_CITIES

# Windows consoles often use a legacy codepage that can't print every
# Turkish/Unicode character; force UTF-8 output so a print never crashes.
# (Guarded because Jupyter's stdout replacement doesn't support reconfigure,
# and doesn't need it — it already handles Unicode natively.)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

INPUT_PATH = "data/raw/suppliers_raw.csv"
OUTPUT_PATH = "data/processed/suppliers_clean.csv"

ALL_CITIES = sorted(set(INDUSTRIAL_CITIES + OTHER_CITIES))

DATE_FORMATS = ["%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%y"]

# Explicit maps for the small, enumerated category columns. Matching against
# a fixed list of known literal variants is simpler and safer here than
# case-insensitive comparison, which is exactly what breaks on Turkish ı/İ.
COMPANY_SIZE_MAP = {
    "küçük": "Small", "kucuk": "Small", "small": "Small",
    "orta": "Medium", "medium": "Medium",
    "büyük": "Large", "buyuk": "Large", "large": "Large",
}
ISO_CERTIFIED_MAP = {
    "evet": True, "yes": True, "1": True, "true": True,
    "hayır": False, "hayir": False, "no": False, "0": False, "false": False,
}

# Map Turkish letters to a plain-ASCII key before lowercasing, so that
# comparisons don't depend on Python's non-Turkish-aware .lower()/.upper().
_TR_FOLD = str.maketrans({
    "ş": "s", "Ş": "s", "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ı": "i", "İ": "i", "I": "i",
})


def _strip_combining_marks(text: str) -> str:
    """Removes stray combining diacritics, notably the combining dot above
    (U+0307) that Python's Unicode-correct-but-Turkish-incorrect str.lower()
    leaves behind when lowercasing 'İ' (it produces 'i' + U+0307 instead of
    plain 'i')."""
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def fold(text: str) -> str:
    """ASCII-folded, lowercased key used only for matching, never for display."""
    text = str(text).strip().translate(_TR_FOLD)
    return _strip_combining_marks(text).lower()


def parse_messy_number(value) -> float:
    """Parses a number written either Turkish-style (1.234,56) or plain
    (1234.56) into a float."""
    if pd.isna(value):
        return np.nan
    text = str(value).strip()
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    return float(text)


def parse_messy_date(value):
    """Tries each known raw date format in turn; returns NaT if none match."""
    if pd.isna(value):
        return pd.NaT
    text = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return pd.to_datetime(text, format=fmt)
        except ValueError:
            continue
    return pd.NaT


def map_category(value, lookup: dict, column_name: str):
    """Maps a raw category value to its canonical form via an exact-match
    lookup on the folded key. Warns (instead of silently guessing) on any
    value that doesn't match a known variant."""
    if pd.isna(value):
        return np.nan
    key = fold(value)
    if key not in lookup:
        print(f"WARNING: unrecognized value '{value}' in column '{column_name}' -> set to NaN")
        return np.nan
    return lookup[key]


def clean_free_text_city_or_sector(value, canonical_values: list, column_name: str):
    """Restores a messy city/sector value to its correct canonical Turkish
    spelling by matching on a folded (accent/case-insensitive) key. This only
    works because city/sector come from a small closed list."""
    if pd.isna(value):
        return np.nan
    lookup = {fold(v): v for v in canonical_values}
    key = fold(value)
    if key not in lookup:
        print(f"WARNING: unrecognized value '{value}' in column '{column_name}' -> set to NaN")
        return np.nan
    return lookup[key]


# Company-name legal suffix tokens get a fixed canonical spelling rather than
# generic title-casing, since title-casing "a.ş." word-by-word would not
# reliably produce "A.Ş.".
SUFFIX_CANONICAL = {
    "a.s.": "A.Ş.", "as.": "A.Ş.",
    "ltd.": "Ltd.",
    "sti.": "Şti.",
    "tic.": "Tic.",
    "san.": "San.",
    "ve": "ve",
    "holding": "Holding",
    "grup": "Grup",
}


def clean_company_name(value) -> str:
    """Normalizes whitespace and casing. Cannot recover Turkish characters
    that were already dropped upstream (e.g. 'san.' vs 'şan.' are ambiguous
    once diacritics are lost) — that data loss is a genuine limitation, not
    something to silently guess around."""
    if pd.isna(value):
        return np.nan
    words = str(value).strip().split()
    cleaned_words = []
    for word in words:
        key = fold(word)
        if key in SUFFIX_CANONICAL:
            cleaned_words.append(SUFFIX_CANONICAL[key])
            continue
        # Turkish-correct capitalization: the folded key already lost casing;
        # rebuild it using the original word's own characters so any
        # diacritics still present in this word are preserved.
        lower_word = _strip_combining_marks(word.lower())
        first_char = "İ" if lower_word[0] == "i" else lower_word[0].upper()
        cleaned_words.append(first_char + lower_word[1:])
    return " ".join(cleaned_words)


def main():
    df = pd.read_csv(INPUT_PATH, encoding="utf-8-sig")

    df["company_name"] = df["company_name"].apply(clean_company_name)
    df["sector"] = df["sector"].apply(lambda v: clean_free_text_city_or_sector(v, SECTOR_NAMES, "sector"))
    df["city"] = df["city"].apply(lambda v: clean_free_text_city_or_sector(v, ALL_CITIES, "city"))
    df["company_size"] = df["company_size"].apply(lambda v: map_category(v, COMPANY_SIZE_MAP, "company_size"))
    df["iso_certified"] = df["iso_certified"].apply(lambda v: map_category(v, ISO_CERTIFIED_MAP, "iso_certified"))

    df["founded_year"] = pd.to_numeric(df["founded_year"], errors="coerce").astype("Int64")

    for col in ["annual_purchase_volume_tl", "price_q1", "price_q2", "price_q3", "price_q4"]:
        df[col] = df[col].apply(parse_messy_number)

    for col in ["late_orders_last_year", "units_returned_last_year", "payment_terms_days"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    for col in ["contract_start_date", "last_audit_date"]:
        df[col] = df[col].apply(parse_messy_date)

    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print()
    print(f"Cleaned {len(df)} rows -> {OUTPUT_PATH}")
    print()
    print("Missing values per column after cleaning:")
    print(df.isna().sum())


if __name__ == "__main__":
    main()
