# -*- coding: utf-8 -*-
"""
AI-assisted source profile drafting.

Onboarding a new ERP export currently means a human reading a sample file and
hand-writing a `config/erp_profiles/*.yaml` profile (see engine.py / SKILL.md
in this package). This module automates the *first draft* of that: it turns
a sample of a new raw export into a precise prompt — built directly from this
project's own Pydantic schema, so the model is told the exact shape expected,
not left to guess — and validates whatever profile comes back against that
same schema before it's ever used.

Deliberately NOT built as "call an API and trust the output blindly":
  - No API key or `anthropic` package on the machine? The prompt is written
    to a file the user can paste into any AI assistant (Claude.ai, Claude
    Code, ChatGPT, ...) by hand — the feature still works, just not
    end-to-end automatically. This is the path that works for anyone who
    clones this repo, regardless of what they have installed.
  - API key available? `--auto` calls the Anthropic API directly for a
    one-command draft.
  - Either way, the response is run through the *same* Pydantic validation
    every hand-written profile goes through (src/cleaning/profile.py) before
    it's saved — a draft that doesn't validate is reported as an error, not
    silently written to disk. The AI drafts; the schema (and a human
    reviewing the diff) still decides.

This is the intentional design referenced in docs/research_v2.md's "AI
should accelerate the reusable-profile workflow, not replace the transparent
scoring logic" discussion — see that file for why the scoring algorithm
itself deliberately does NOT use AI/ML.
"""

import json
import os
import re
from pathlib import Path

import pandas as pd
import yaml
from pydantic import ValidationError

from .profile import SourceProfile

PROMPT_TEMPLATE = """\
You are drafting a data-source "profile" for a supplier-data cleaning pipeline.

The pipeline's cleaning engine is completely generic — it knows nothing about \
any specific ERP or export format. All source-specific knowledge (which raw \
column maps to which canonical field, what date formats are used, whether \
numbers use a Turkish comma-decimal or plain period-decimal convention, which \
raw text values a category column can contain) lives in a declarative YAML \
profile matching the JSON Schema below.

## Target JSON Schema for the profile

```json
{schema_json}
```

## Canonical target field names this project understands

{canonical_fields}

## Sample of the raw source file to profile ("{source_name}")

Columns: {columns}

First {n_rows} rows:
```
{sample_rows}
```

## Your task

Output ONLY a single YAML document (no prose, no markdown fences) that is a \
valid instance of the schema above, profiling this source. Map as many raw \
columns as you can confidently identify to the canonical field names listed. \
For any category column (e.g. a size/status/certification label), include \
every distinct raw value you can see in the sample in `category_maps`, \
mapped to a sensible canonical value — do not invent canonical values that \
aren't implied by the data. If you are not confident about a column's \
meaning, leave it out of `column_mapping` rather than guessing — an omitted \
column simply passes through unmodified, which is safer than a wrong \
mapping.
"""


def build_profile_draft_prompt(sample_df: pd.DataFrame, source_name: str, n_rows: int = 8) -> str:
    """Builds the full prompt for drafting a profile from a sample DataFrame."""
    schema_json = json.dumps(SourceProfile.model_json_schema(), indent=2, ensure_ascii=False)
    canonical_fields = (
        "supplier_id, company_name, sector, city, company_size, founded_year, "
        "employee_count, vkn, supplier_annual_revenue_tl, annual_purchase_volume_tl, "
        "total_orders_last_year, late_orders_last_year, price_q1, price_q2, price_q3, "
        "price_q4, units_shipped_last_year, units_returned_last_year, "
        "contract_start_date, last_audit_date, payment_terms_days, iso_certified"
    )
    sample = sample_df.head(n_rows)
    return PROMPT_TEMPLATE.format(
        schema_json=schema_json,
        canonical_fields=canonical_fields,
        source_name=source_name,
        columns=", ".join(str(c) for c in sample_df.columns),
        n_rows=len(sample),
        sample_rows=sample.to_csv(index=False),
    )


def extract_yaml(response_text: str) -> str:
    """Strips a markdown code fence around the YAML if the model added one
    despite being asked not to — models do this often enough that handling
    it is more robust than a strict "no fences allowed" assumption."""
    fenced = re.search(r"```(?:yaml)?\s*\n(.*?)\n```", response_text, re.DOTALL)
    return fenced.group(1) if fenced else response_text.strip()


def validate_profile_draft(response_text: str) -> SourceProfile:
    """Parses and validates an AI-drafted profile. Raises with a clear
    message (never silently accepts something malformed) if it doesn't
    match the schema — the same validation every hand-written profile goes
    through, per this module's docstring."""
    yaml_text = extract_yaml(response_text)
    try:
        raw = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        raise ValueError(f"AI response was not valid YAML:\n{e}\n\n--- raw response ---\n{response_text}") from e
    try:
        return SourceProfile.model_validate(raw)
    except ValidationError as e:
        raise ValueError(f"AI-drafted profile failed schema validation:\n{e}") from e


def call_anthropic_api(prompt: str, model: str = "claude-sonnet-4-5") -> str:
    """Calls the Anthropic API directly, for the --auto path. Requires the
    `anthropic` package and an ANTHROPIC_API_KEY environment variable —
    raises a clear, actionable error if either is missing rather than a
    confusing stack trace."""
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError(
            "The --auto flag needs the 'anthropic' package: pip install anthropic"
        ) from e
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "The --auto flag needs an ANTHROPIC_API_KEY environment variable. "
            "Without one, use the default (non---auto) mode instead: it writes "
            "the prompt to a file you can paste into any AI assistant by hand."
        )
    client = anthropic.Anthropic()
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in message.content if hasattr(block, "text"))
