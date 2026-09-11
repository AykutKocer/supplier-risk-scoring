# -*- coding: utf-8 -*-
"""Tests for the VKN checksum algorithm, using the exact valid/invalid
example numbers published alongside the reference implementation this was
ported from (see src/cleaning/vkn.py docstring) — this is what lets us claim
the algorithm is actually correct, not just plausible-looking."""

import random

import pytest

from cleaning import vkn

KNOWN_VALID = ["3973535717", "2037637860", "2823097943", "2012460224"]
KNOWN_INVALID = ["3973535711", "9999999999"]


@pytest.mark.parametrize("number", KNOWN_VALID)
def test_known_valid_vkns_pass(number):
    assert vkn.is_valid(number) is True


@pytest.mark.parametrize("number", KNOWN_INVALID)
def test_known_invalid_vkns_fail(number):
    assert vkn.is_valid(number) is False


def test_wrong_length_is_invalid():
    assert vkn.is_valid("123") is False
    assert vkn.is_valid("12345678901") is False


def test_non_numeric_is_invalid():
    assert vkn.is_valid("123456789a") is False


def test_generate_produces_a_checksum_valid_vkn():
    rng = random.Random(42)
    for _ in range(200):
        number = vkn.generate(rng)
        assert vkn.is_valid(number), f"generated VKN {number} failed its own checksum"


def test_generate_first_digit_is_never_zero():
    rng = random.Random(0)
    for _ in range(200):
        assert vkn.generate(rng)[0] != "0"
