# -*- coding: utf-8 -*-
"""
Turkish VKN (Vergi Kimlik Numarası / Tax Identification Number) generation
and checksum validation.

A VKN is 10 digits: the first 9 are the base number, the 10th is a check
digit computed from them by a real, documented algorithm — not a random or
sequential number. This module implements that algorithm so this project can
(a) generate synthetic VKNs that pass real-world validation, the way a
well-built test fixture should, and (b) validate a VKN found in raw data as
an actual data-quality check, not just a "10 digits present" formatting
check.

Algorithm ported from a community reference implementation (verified against
its own published valid/invalid examples — see tests/test_vkn.py):
https://gist.github.com/sadikay/7847f15100efbdaf036fbec937639857
"""

import random


def compute_check_digit(first_nine_digits: str) -> int:
    """Computes the 10th (check) digit for a 9-digit VKN base."""
    if len(first_nine_digits) != 9 or not first_nine_digits.isdigit():
        raise ValueError("first_nine_digits must be exactly 9 digits")

    total = 0
    for i, ch in enumerate(first_nine_digits):
        x = int(ch) + 9 - i
        mod = x % 10
        if mod == 9:
            total += 9
        else:
            power = 2 ** (9 - i)
            total += (mod * power) % 9

    return (10 - total % 10) % 10


def is_valid(vkn: str) -> bool:
    """Whether `vkn` is a syntactically correct, checksum-valid 10-digit VKN."""
    if not isinstance(vkn, str) or len(vkn) != 10 or not vkn.isdigit():
        return False
    return compute_check_digit(vkn[:9]) == int(vkn[9])


def generate(rng: random.Random | None = None) -> str:
    """Generates a random but checksum-valid 10-digit VKN — for synthetic
    test data, not a real taxpayer's number. The first digit is kept
    non-zero so the result always reads as a genuine 10-digit number."""
    rng = rng or random
    first_nine = str(rng.randint(1, 9)) + "".join(str(rng.randint(0, 9)) for _ in range(8))
    return first_nine + str(compute_check_digit(first_nine))
