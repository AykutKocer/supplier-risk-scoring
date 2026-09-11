# -*- coding: utf-8 -*-
"""
Cleans a raw supplier export using a profile-driven, source-agnostic engine
(`src/cleaning/`) and writes a standardized version to data/processed/.

v1 of this script hardcoded every parsing rule for one specific messiness
pattern (this project's own synthetic generator). v2 separates that into two
pieces: a generic engine (src/cleaning/engine.py) that knows nothing about any
particular data source, and a declarative profile
(config/erp_profiles/*.yaml) that describes one source's specific quirks —
column names, date formats, decimal-separator convention, category label
variants. Supporting a new source system (a different ERP export, a
different company's spreadsheet habits) means writing a new profile file,
not new Python code.

Usage:
    python src/clean_suppliers.py                              # uses the default profile below
    python src/clean_suppliers.py --profile config/erp_profiles/sap_export_example.yaml --input my_export.csv
"""

import argparse
import sys

import pandas as pd

from cleaning import clean_with_profile, load_profile, vkn as vkn_module

# Windows consoles often use a legacy codepage that can't print every
# Turkish/Unicode character; force UTF-8 output so a print never crashes.
# (Guarded because Jupyter's stdout replacement doesn't support reconfigure,
# and doesn't need it — it already handles Unicode natively.)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_PROFILE_PATH = "config/erp_profiles/synthetic_generator.yaml"
DEFAULT_INPUT_PATH = "data/raw/suppliers_raw.csv"
DEFAULT_OUTPUT_PATH = "data/processed/suppliers_clean.csv"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=DEFAULT_PROFILE_PATH, help="Path to a source profile YAML file.")
    parser.add_argument("--input", default=DEFAULT_INPUT_PATH, help="Path to the raw CSV export to clean.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH, help="Where to write the cleaned CSV.")
    args = parser.parse_args()

    profile = load_profile(args.profile)
    print(f"Using profile: {profile.name} — {profile.description}")

    df = pd.read_csv(args.input, encoding=profile.encoding)
    cleaned = clean_with_profile(df, profile)

    # VKN checksum validation is a genuine Turkish business-rule check, not a
    # generic formatting concern the engine can express — it's applied here
    # as a bespoke step on top of the generic engine's output, the same way
    # any project-specific validation would layer on top of the reusable
    # cleaning core. A failed checksum is flagged, never silently "fixed"
    # (there's no way to recover the correct digits from a corrupted one).
    if "vkn" in cleaned.columns:
        cleaned["vkn_valid"] = cleaned["vkn"].apply(
            lambda v: vkn_module.is_valid(str(v)) if pd.notna(v) else pd.NA
        )

    cleaned.to_csv(args.output, index=False, encoding="utf-8-sig")

    print()
    print(f"Cleaned {len(cleaned)} rows -> {args.output}")
    print()
    print("Missing values per column after cleaning:")
    print(cleaned.isna().sum())
    if "vkn_valid" in cleaned.columns:
        n_invalid = (cleaned["vkn_valid"] == False).sum()  # noqa: E712 (nullable bool, `is False` doesn't broadcast)
        print()
        print(f"VKN checksum check: {n_invalid} of {cleaned['vkn'].notna().sum()} present VKNs failed validation "
              f"(flagged in 'vkn_valid', not silently corrected).")


if __name__ == "__main__":
    main()
