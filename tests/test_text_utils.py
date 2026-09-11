# -*- coding: utf-8 -*-
"""Unit tests for the source-agnostic text/number/date parsing helpers.

These lock in behavior that was discovered the hard way while building v1
(the Turkish 'İ'.lower() Unicode bug in particular) — a regression here
would silently reintroduce a bug that already cost real debugging time once.
"""

import math

import pandas as pd
import pytest

from cleaning.text_utils import (
    fold,
    map_category,
    parse_messy_date,
    parse_messy_number,
    restore_from_canonical_list,
    title_case_free_text,
)


class TestFold:
    def test_basic_ascii_case_insensitive(self):
        assert fold("Small") == fold("SMALL") == fold("small")

    def test_turkish_diacritics_fold_to_ascii(self):
        assert fold("Şirket") == fold("SIRKET") == fold("sirket")

    def test_turkish_i_lower_unicode_bug_is_handled(self):
        # 'İ'.lower() in plain Python produces 'i' + U+0307 (combining dot
        # above), not plain 'i' — the exact bug found while building v1.
        # fold() must still treat these as equal to a plain-ascii spelling.
        assert fold("İSTANBUL") == fold("Istanbul") == fold("istanbul")

    def test_whitespace_is_stripped(self):
        assert fold("  Ankara  ") == fold("Ankara")


class TestParseMessyNumber:
    def test_plain_international_format(self):
        assert parse_messy_number("1234.56") == pytest.approx(1234.56)

    def test_turkish_format_with_thousands_separator(self):
        assert parse_messy_number("1.234.567,89") == pytest.approx(1234567.89)

    def test_turkish_format_no_thousands_separator(self):
        assert parse_messy_number("234,56") == pytest.approx(234.56)

    def test_missing_value_returns_nan(self):
        assert math.isnan(parse_messy_number(None))
        assert math.isnan(parse_messy_number(float("nan")))


class TestParseMessyDate:
    FORMATS = ["%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%y"]

    @pytest.mark.parametrize("raw", ["15.03.2021", "2021-03-15", "15/03/2021"])
    def test_recognized_formats_parse_to_same_date(self, raw):
        result = parse_messy_date(raw, self.FORMATS)
        assert result == pd.Timestamp("2021-03-15")

    def test_unrecognized_format_returns_nat(self):
        assert pd.isna(parse_messy_date("not a date", self.FORMATS))

    def test_missing_value_returns_nat(self):
        assert pd.isna(parse_messy_date(None, self.FORMATS))


class TestMapCategory:
    LOOKUP = {"kucuk": "Small", "buyuk": "Large"}

    def test_matches_known_variant_case_insensitively(self):
        assert map_category("KÜÇÜK", self.LOOKUP, "company_size") == "Small"

    def test_unknown_value_returns_nan_not_a_guess(self):
        assert pd.isna(map_category("unknown_value", self.LOOKUP, "company_size"))

    def test_missing_value_passes_through(self):
        assert pd.isna(map_category(None, self.LOOKUP, "company_size"))


class TestRestoreFromCanonicalList:
    CANONICAL = ["Tekstil", "Elektronik", "İnşaat Malzemeleri"]

    def test_restores_correct_diacritics_from_ascii_dropped_input(self):
        assert restore_from_canonical_list("insaat malzemeleri", self.CANONICAL, "sector") == "İnşaat Malzemeleri"

    def test_restores_from_shouted_case(self):
        assert restore_from_canonical_list("TEKSTIL", self.CANONICAL, "sector") == "Tekstil"

    def test_value_outside_the_list_returns_nan(self):
        assert pd.isna(restore_from_canonical_list("Otomotiv", self.CANONICAL, "sector"))


class TestTitleCaseFreeText:
    SUFFIXES = {"a.s.": "A.Ş.", "ltd.": "Ltd.", "sti.": "Şti."}

    def test_normalizes_casing_and_preserves_suffix(self):
        assert title_case_free_text("akar plastik ltd. sti.", self.SUFFIXES) == "Akar Plastik Ltd. Şti."

    def test_turkish_i_capitalization(self):
        # first letter 'i' should become dotted capital İ, not ascii 'I'
        assert title_case_free_text("istanbul metal", {}) == "İstanbul Metal"

    def test_does_not_guess_back_already_lost_diacritics(self):
        # 'san.' could originally have been 'şan.' or genuinely 'san.' —
        # once the diacritic is gone this function must not invent one.
        assert title_case_free_text("demir celik san.", {}) == "Demir Celik San."
