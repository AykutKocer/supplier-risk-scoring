# -*- coding: utf-8 -*-
"""
CLI: derive risk-scoring weights from pairwise comparisons (AHP) and report
how they compare to the asserted defaults in config/scoring_weights.yaml.

    python src/derive_ahp_weights.py            # report only (default)
    python src/derive_ahp_weights.py --apply     # also writes the derived
                                                  # weights into
                                                  # config/scoring_weights.yaml

By default this is a dry run: it never changes config/scoring_weights.yaml
on its own. Weights are a business decision (see that file's own header
comment) — AHP is offered here as a rigorous, consistency-checked way to
derive or cross-check them, not as something that should silently overwrite
a human's own judgment.
"""

import argparse
import sys

import yaml

from ahp import CONSISTENCY_RATIO_THRESHOLD, derive_weights_from_config

AHP_CONFIG_PATH = "config/ahp_pairwise_comparisons.yaml"
SCORING_WEIGHTS_PATH = "config/scoring_weights.yaml"


def print_report(result: dict, current_weights: dict) -> None:
    print("Pairwise comparison matrix:")
    header = "".join(f"{c[:14]:>16}" for c in result["criteria"])
    print(" " * 26 + header)
    for name, row in zip(result["criteria"], result["matrix"]):
        formatted = "".join(f"{v:16.2f}" for v in row)
        print(f"{name:<26}{formatted}")
    print()

    print(f"{'Criterion':<28}{'AHP weight':>12}{'Current weight':>16}{'Difference':>13}")
    for criterion, weight in result["weights"].items():
        current = current_weights.get(criterion)
        current_str = f"{current:.3f}" if current is not None else "n/a"
        diff_str = f"{weight - current:+.3f}" if current is not None else "n/a"
        print(f"{criterion:<28}{weight:>12.3f}{current_str:>16}{diff_str:>13}")
    print()

    status = "OK (consistent)" if result["is_consistent"] else "FAILS — revisit the pairwise judgments"
    print(f"lambda_max = {result['lambda_max']:.4f}   "
          f"Consistency Index = {result['consistency_index']:.4f}   "
          f"Consistency Ratio = {result['consistency_ratio']:.4f}  "
          f"(threshold {CONSISTENCY_RATIO_THRESHOLD}) -> {status}")


def apply_weights(weights: dict, consistency_ratio: float) -> None:
    with open(SCORING_WEIGHTS_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config["weights"] = {k: round(float(v), 4) for k, v in weights.items()}

    with open(SCORING_WEIGHTS_PATH, "w", encoding="utf-8") as f:
        f.write(
            "# Supplier risk scoring configuration\n"
            "# =============================================================================\n"
            "# Weights below were derived via AHP (Analytic Hierarchy Process) pairwise\n"
            f"# comparisons in config/ahp_pairwise_comparisons.yaml (Consistency Ratio "
            f"{consistency_ratio:.4f},\n"
            "# under the 0.10 threshold — see src/ahp.py and README.md 'AHP-derived\n"
            "# weights'). Re-run `python src/derive_ahp_weights.py --apply` after editing\n"
            "# that file to regenerate this section.\n"
            "#\n"
            "# Requirement: the four weights must add up to 1.0. The scoring script\n"
            "# validates this and raises an error if they don't.\n\n"
        )
        yaml.dump({"weights": config["weights"]}, f, sort_keys=False, default_flow_style=False)
        f.write(
            "\n# Cutoffs that turn the final 0-100 risk score into a Low/Medium/High label.\n"
            "# Unchanged by AHP — see config/scoring_weights.yaml's git history for the\n"
            "# original percentile-threshold rationale.\n"
        )
        yaml.dump({"risk_level_thresholds": config["risk_level_thresholds"]}, f, sort_keys=False, default_flow_style=False)

    print(f"\nWrote AHP-derived weights to {SCORING_WEIGHTS_PATH}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                         help=f"Write the derived weights into {SCORING_WEIGHTS_PATH} (default: report only).")
    args = parser.parse_args()

    result = derive_weights_from_config(AHP_CONFIG_PATH)
    with open(SCORING_WEIGHTS_PATH, encoding="utf-8") as f:
        current_weights = yaml.safe_load(f)["weights"]

    print_report(result, current_weights)

    if args.apply:
        if not result["is_consistent"]:
            print(f"\nRefusing to apply: Consistency Ratio {result['consistency_ratio']:.4f} "
                  f"exceeds the {CONSISTENCY_RATIO_THRESHOLD} threshold. Revisit the pairwise "
                  f"judgments in {AHP_CONFIG_PATH} first.")
            sys.exit(1)
        apply_weights(result["weights"], result["consistency_ratio"])


if __name__ == "__main__":
    main()
