# -*- coding: utf-8 -*-
"""Tests for AI-assisted profile drafting. Doesn't call any real API (no
network access, no API key required to run this suite) — exercises the
prompt construction and the validation path that any AI-assistant response,
real or hand-simulated, has to pass through before it's trusted."""

import os

import pandas as pd
import pytest

from cleaning.ai_profile_assist import (
    build_profile_draft_prompt,
    call_anthropic_api,
    extract_yaml,
    validate_profile_draft,
)

SAMPLE_DF = pd.DataFrame({
    "Tedarikci Kodu": ["TED001", "TED002"],
    "Firma Unvani": ["Akin Tekstil Ltd. Sti.", "Bozkurt Metal A.S."],
    "Il": ["Istanbul", "Ankara"],
})


class TestBuildProfileDraftPrompt:
    def test_includes_the_real_schema_not_a_placeholder(self):
        prompt = build_profile_draft_prompt(SAMPLE_DF, "test_source")
        # Spot-check a few field names that only appear if the *actual*
        # Pydantic schema (not a hand-typed stand-in) was serialized in.
        assert "column_mapping" in prompt
        assert "closed_list_columns" in prompt
        assert "SourceProfile" in prompt

    def test_includes_the_sample_columns_and_source_name(self):
        prompt = build_profile_draft_prompt(SAMPLE_DF, "test_source")
        assert "Tedarikci Kodu" in prompt
        assert "Firma Unvani" in prompt
        assert "test_source" in prompt

    def test_includes_the_canonical_field_vocabulary(self):
        prompt = build_profile_draft_prompt(SAMPLE_DF, "test_source")
        assert "company_name" in prompt
        assert "supplier_dependency" not in prompt  # not a real canonical field name

    def test_instructs_against_guessing(self):
        prompt = build_profile_draft_prompt(SAMPLE_DF, "test_source")
        assert "guess" in prompt.lower()


class TestExtractYaml:
    def test_plain_yaml_passes_through(self):
        text = "name: foo\ndescription: bar\n"
        assert extract_yaml(text) == text.strip()

    def test_strips_markdown_code_fence(self):
        text = "```yaml\nname: foo\ndescription: bar\n```"
        assert extract_yaml(text) == "name: foo\ndescription: bar"

    def test_strips_unlabeled_code_fence(self):
        text = "```\nname: foo\ndescription: bar\n```"
        assert extract_yaml(text) == "name: foo\ndescription: bar"


class TestValidateProfileDraft:
    VALID_DRAFT = """
name: my_erp
description: A test profile.
column_mapping:
  - source_name: Firma Unvani
    canonical_name: company_name
"""

    def test_accepts_a_valid_draft(self):
        profile = validate_profile_draft(self.VALID_DRAFT)
        assert profile.name == "my_erp"
        assert profile.column_mapping[0].canonical_name == "company_name"

    def test_accepts_a_fenced_valid_draft(self):
        fenced = f"```yaml\n{self.VALID_DRAFT.strip()}\n```"
        profile = validate_profile_draft(fenced)
        assert profile.name == "my_erp"

    def test_rejects_malformed_yaml_with_clear_error(self):
        with pytest.raises(ValueError, match="not valid YAML"):
            validate_profile_draft("name: [unclosed")

    def test_rejects_schema_violation_with_clear_error(self):
        # Missing the required 'description' field.
        with pytest.raises(ValueError, match="schema validation"):
            validate_profile_draft("name: my_erp\n")

    def test_rejects_duplicate_canonical_mapping_targets(self):
        bad = """
name: my_erp
description: A test profile.
column_mapping:
  - source_name: A
    canonical_name: company_name
  - source_name: B
    canonical_name: company_name
"""
        with pytest.raises(ValueError, match="schema validation"):
            validate_profile_draft(bad)


class TestCallAnthropicApi:
    def test_raises_clear_error_without_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        pytest.importorskip("anthropic")  # only meaningful once the package is installed
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            call_anthropic_api("some prompt")

    def test_raises_clear_error_without_package_installed(self, monkeypatch):
        if _anthropic_is_installed():
            pytest.skip("anthropic package is installed in this environment")
        with pytest.raises(RuntimeError, match="anthropic"):
            call_anthropic_api("some prompt")


def _anthropic_is_installed() -> bool:
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False
