# -*- coding: utf-8 -*-
"""
Pydantic schema for a "source profile" — a declarative description of how one
specific data source (a specific ERP's export, or a specific company's
spreadsheet habits) needs to be parsed and standardized.

The goal: adding support for a new source system means writing a new
`config/erp_profiles/*.yaml` file, not new Python code. See
`config/erp_profiles/` for real examples (synthetic generator output) and
illustrative ones (SAP-style, Logo/Netsis-style) built from public
documentation, clearly labeled as such since they were never run against a
real export from those systems.
"""

from typing import Literal, Union

from pydantic import BaseModel, Field, model_validator


class ColumnMapping(BaseModel):
    """Renames one raw source column to this project's canonical name."""
    source_name: str
    canonical_name: str


class DateColumnSpec(BaseModel):
    canonical_name: str
    formats: list[str] = Field(
        default_factory=list,
        description="strptime-compatible formats, tried in order until one matches.",
    )


class NumericColumnSpec(BaseModel):
    canonical_name: str
    decimal_style: Literal["auto", "turkish", "international"] = "auto"
    target_dtype: Literal["float", "Int64"] = "float"


class CategoryMap(BaseModel):
    """Maps every known raw variant of a category column to one canonical
    value, e.g. {'küçük': 'Small', 'KÜÇÜK': 'Small', 'Small': 'Small'}."""
    canonical_name: str
    value_map: dict[str, Union[str, bool]]


class FreeTextTitleCaseColumn(BaseModel):
    """A free-text column (e.g. company_name) normalized to consistent
    whitespace/casing, with known legal-suffix tokens (e.g. 'a.ş.' -> 'A.Ş.',
    'gmbh' -> 'GmbH') preserved exactly rather than title-cased letter by
    letter. Cannot recover diacritics already lost upstream — see
    text_utils.title_case_free_text."""
    canonical_name: str
    known_suffixes: dict[str, str] = Field(default_factory=dict)


class ClosedListColumn(BaseModel):
    """A column whose raw values should be restored to a known canonical
    spelling by fuzzy (accent/case-insensitive) matching against a fixed
    list — e.g. sector or city names. Only valid for genuinely closed lists;
    see text_utils.restore_from_canonical_list for why free text can't use
    this approach."""
    canonical_name: str
    canonical_values: list[str]


class SourceProfile(BaseModel):
    """A complete description of one source system's export quirks."""
    name: str
    description: str
    encoding: str = "utf-8-sig"
    column_mapping: list[ColumnMapping] = Field(default_factory=list)
    date_columns: list[DateColumnSpec] = Field(default_factory=list)
    numeric_columns: list[NumericColumnSpec] = Field(default_factory=list)
    category_maps: list[CategoryMap] = Field(default_factory=list)
    closed_list_columns: list[ClosedListColumn] = Field(default_factory=list)
    free_text_title_case_columns: list[FreeTextTitleCaseColumn] = Field(default_factory=list)
    required_canonical_columns: list[str] = Field(
        default_factory=list,
        description="Canonical columns that must be present after renaming, or the profile doesn't actually match this file.",
    )

    @model_validator(mode="after")
    def _no_duplicate_canonical_targets(self) -> "SourceProfile":
        targets = [m.canonical_name for m in self.column_mapping]
        dupes = {t for t in targets if targets.count(t) > 1}
        if dupes:
            raise ValueError(f"column_mapping maps multiple source columns to the same canonical name(s): {dupes}")
        return self
