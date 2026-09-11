# -*- coding: utf-8 -*-
"""Every profile in config/erp_profiles/ must at least be schema-valid,
whether or not it's been run against a real export file yet (the example
profiles for SAP/Logo-Netsis are illustrative — see their own docstrings —
but should still never be malformed YAML or violate the schema)."""

from pathlib import Path

import pytest

from cleaning import load_profile

PROFILES_DIR = Path(__file__).resolve().parent.parent / "config" / "erp_profiles"
PROFILE_PATHS = sorted(PROFILES_DIR.glob("*.yaml"))


@pytest.mark.parametrize("path", PROFILE_PATHS, ids=lambda p: p.name)
def test_profile_is_schema_valid(path):
    profile = load_profile(path)
    assert profile.name
    assert profile.description


def test_at_least_one_profile_exists():
    assert PROFILE_PATHS, f"No profile YAML files found in {PROFILES_DIR}"


def test_no_two_profiles_share_a_name():
    names = [load_profile(p).name for p in PROFILE_PATHS]
    assert len(names) == len(set(names)), f"Duplicate profile names: {names}"
