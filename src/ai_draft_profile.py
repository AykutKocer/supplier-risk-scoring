# -*- coding: utf-8 -*-
"""
AI-assisted first draft of a new ERP source profile.

Three ways to use this, depending on what's available on your machine:

1) No API key needed (works for anyone who clones this repo):
    python src/ai_draft_profile.py --sample my_export_sample.csv --name my_erp
    # -> writes config/erp_profiles/my_erp.prompt.txt
    # Paste that file's contents into any AI assistant (Claude.ai, Claude
    # Code, ChatGPT, ...), save its reply to a file, then:
    python src/ai_draft_profile.py --from-response reply.txt --name my_erp
    # -> validates the draft and writes config/erp_profiles/my_erp.yaml

2) Fully automatic, if you have `pip install anthropic` and an
   ANTHROPIC_API_KEY environment variable set:
    python src/ai_draft_profile.py --sample my_export_sample.csv --name my_erp --auto
    # -> writes config/erp_profiles/my_erp.yaml directly

Either way, the draft is validated against this project's own SourceProfile
schema (src/cleaning/profile.py) before being written — an invalid draft is
reported as an error, never silently saved. Always review a generated
profile before trusting it on real data, the same as you would review any
other AI-assisted code.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

from cleaning.ai_profile_assist import (
    build_profile_draft_prompt,
    call_anthropic_api,
    validate_profile_draft,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROFILES_DIR = Path("config/erp_profiles")


def save_profile(profile, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(
            profile.model_dump(exclude_none=True),
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=100,
        )
    print(f"Wrote validated profile -> {output_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample", help="Path to a sample raw CSV export to profile.")
    parser.add_argument("--name", required=True, help="Short name for this source (used in filenames).")
    parser.add_argument("--auto", action="store_true", help="Call the Anthropic API directly instead of writing a prompt file.")
    parser.add_argument("--from-response", help="Path to a file containing an AI assistant's reply, to validate and save.")
    parser.add_argument("--rows", type=int, default=8, help="How many sample rows to include in the prompt (default 8).")
    args = parser.parse_args()

    if args.from_response:
        response_text = Path(args.from_response).read_text(encoding="utf-8")
        try:
            profile = validate_profile_draft(response_text)
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)
        save_profile(profile, PROFILES_DIR / f"{args.name}.yaml")
        return

    if not args.sample:
        parser.error("--sample is required unless --from-response is given")

    sample_df = pd.read_csv(args.sample, encoding="utf-8-sig")
    prompt = build_profile_draft_prompt(sample_df, args.name, n_rows=args.rows)

    if args.auto:
        try:
            response_text = call_anthropic_api(prompt)
        except RuntimeError as e:
            print(f"ERROR: {e}")
            sys.exit(1)
        try:
            profile = validate_profile_draft(response_text)
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)
        save_profile(profile, PROFILES_DIR / f"{args.name}.yaml")
    else:
        prompt_path = PROFILES_DIR / f"{args.name}.prompt.txt"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt, encoding="utf-8")
        print(f"Wrote prompt -> {prompt_path}")
        print()
        print("Next: paste that file's contents into any AI assistant, save its reply to a")
        print("file, then run:")
        print(f"    python src/ai_draft_profile.py --from-response <reply_file> --name {args.name}")


if __name__ == "__main__":
    main()
