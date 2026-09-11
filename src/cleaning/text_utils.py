# -*- coding: utf-8 -*-
"""
Source-agnostic text, number, and date parsing helpers.

Extracted from the v1 `clean_suppliers.py` (which hardcoded these rules for
one specific synthetic messiness profile) so they can be reused by the v2
profile-driven cleaning engine against *any* source profile, not just one.

Nothing in this module is specific to a particular ERP export or dataset —
that's the whole point. Source-specific behavior (which date formats to try,
which category labels map to what) lives in `config/erp_profiles/*.yaml`,
not here.
"""

import unicodedata

import numpy as np
import pandas as pd

# Map Turkish letters to a plain-ASCII key before lowercasing, so that
# comparisons don't depend on Python's non-Turkish-aware .lower()/.upper()
# (Python's default case folding mishandles İ/ı — see README "Notable design
# decisions" for the specific bug this works around).
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
    (1234.56) into a float. Auto-detects per value, which is what a mixed-
    convention export (the common real-world case) actually needs."""
    if pd.isna(value):
        return np.nan
    text = str(value).strip()
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    return float(text)


def parse_messy_date(value, formats: list[str]):
    """Tries each format in `formats`, in order; returns NaT if none match."""
    if pd.isna(value):
        return pd.NaT
    text = str(value).strip()
    for fmt in formats:
        try:
            return pd.to_datetime(text, format=fmt)
        except ValueError:
            continue
    return pd.NaT


def map_category(value, lookup: dict, column_name: str, source_name: str = ""):
    """Maps a raw category value to its canonical form via an exact-match
    lookup on the folded key. Warns (instead of silently guessing) on any
    value that doesn't match a known variant for this profile."""
    if pd.isna(value):
        return np.nan
    key = fold(value)
    if key not in lookup:
        label = f"[{source_name}] " if source_name else ""
        print(f"WARNING: {label}unrecognized value '{value}' in column '{column_name}' -> set to NaN")
        return np.nan
    return lookup[key]


def title_case_free_text(value, known_suffixes: dict[str, str]):
    """Normalizes whitespace and casing in a free-text field (e.g. a company
    name), preserving the exact spelling of known legal-suffix tokens
    (looked up by folded key, e.g. {'a.s.': 'A.Ş.'}) rather than
    title-casing them character by character.

    Cannot recover a diacritic that was already lost upstream (e.g. 'san.'
    vs 'şan.' are ambiguous once the character is gone) — that data loss is
    a genuine limitation, not something to silently guess around."""
    if pd.isna(value):
        return np.nan
    words = str(value).strip().split()
    cleaned_words = []
    for word in words:
        key = fold(word)
        if key in known_suffixes:
            cleaned_words.append(known_suffixes[key])
            continue
        lower_word = _strip_combining_marks(word.lower())
        if not lower_word:
            continue
        first_char = "İ" if lower_word[0] == "i" else lower_word[0].upper()
        cleaned_words.append(first_char + lower_word[1:])
    return " ".join(cleaned_words)


def restore_from_canonical_list(value, canonical_values: list, column_name: str, source_name: str = ""):
    """Restores a messy value to its correct canonical spelling by matching
    on a folded (accent/case-insensitive) key. Only works for a closed list
    of known values (e.g. a fixed set of sectors or cities) — free text like
    a company name can't be restored this way if it already lost information
    (see README "Notable design decisions")."""
    if pd.isna(value):
        return np.nan
    lookup = {fold(v): v for v in canonical_values}
    key = fold(value)
    if key not in lookup:
        label = f"[{source_name}] " if source_name else ""
        print(f"WARNING: {label}unrecognized value '{value}' in column '{column_name}' -> set to NaN")
        return np.nan
    return lookup[key]
