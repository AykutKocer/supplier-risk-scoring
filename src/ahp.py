# -*- coding: utf-8 -*-
"""
Analytic Hierarchy Process (AHP) weight derivation — Saaty's standard method
for turning pairwise importance judgments into a consistency-checked set of
weights, instead of asserting them directly.

Why this exists: config/scoring_weights.yaml's default weights (35/25/25/15)
are a defensible but *asserted* rationale (see its own comments). AHP is the
academically standard alternative: a decision-maker states "how much more
important is A than B" for every pair of criteria (config/ahp_pairwise_comparisons.yaml),
and this module derives weights from that matrix via the principal
eigenvector method, plus a Consistency Ratio (CR) that catches self-
contradictory judgments (e.g. A > B, B > C, but C > A) mathematically rather
than by inspection. See docs/research_v2.md section 3.3 and README.md
"AHP-derived weights".

This module does not replace config/scoring_weights.yaml automatically —
see src/derive_ahp_weights.py for the CLI that reports the derived weights
for a human to review and, if they choose, apply.
"""

import sys
from itertools import combinations

import numpy as np
import yaml

# Saaty's Random Index (RI): the average consistency ratio of randomly
# generated reciprocal matrices of a given size, used to normalize the
# Consistency Index into a scale-independent Consistency Ratio. Published in
# Saaty, T.L. (1980), "The Analytic Hierarchy Process". RI is 0 for n <= 2
# because a 1x2 or 2x2 reciprocal matrix is always perfectly consistent.
RANDOM_INDEX = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}

# Saaty's standard threshold: a Consistency Ratio above this means the
# pairwise judgments are too self-contradictory to trust and should be
# revisited, not just noted.
CONSISTENCY_RATIO_THRESHOLD = 0.10


def load_ahp_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_comparison_matrix(config: dict) -> tuple:
    """Builds the full n x n reciprocal pairwise comparison matrix from the
    config's `comparisons` list (which only needs to state each unordered
    pair once). Returns (matrix, criteria_list) with criteria in the order
    given by config['criteria']."""
    criteria = config["criteria"]
    n = len(criteria)
    index = {name: i for i, name in enumerate(criteria)}

    expected_pairs = set(frozenset(pair) for pair in combinations(criteria, 2))
    seen_pairs = set()

    matrix = np.ones((n, n))
    for comp in config["comparisons"]:
        a, b, value = comp["a"], comp["b"], comp["value"]
        if a not in index or b not in index:
            raise ValueError(f"Comparison references unknown criterion: {a!r} or {b!r}")
        pair = frozenset((a, b))
        if pair in seen_pairs:
            raise ValueError(f"Duplicate comparison for pair ({a}, {b})")
        seen_pairs.add(pair)

        i, j = index[a], index[b]
        matrix[i, j] = value
        matrix[j, i] = 1.0 / value

    missing = expected_pairs - seen_pairs
    if missing:
        missing_str = ", ".join(sorted(f"({a}, {b})" for a, b in (tuple(p) for p in missing)))
        raise ValueError(f"Missing comparison(s) for pair(s): {missing_str}")

    return matrix, criteria


def compute_ahp_weights(matrix: np.ndarray) -> np.ndarray:
    """Derives weights via the principal eigenvector method: the eigenvector
    associated with the matrix's largest (real) eigenvalue, normalized to
    sum to 1. This is Saaty's original method (simpler approximations like
    column-normalize-then-average-rows exist, but the eigenvector method is
    the one AHP is actually defined by)."""
    eigvals, eigvecs = np.linalg.eig(matrix)
    principal_index = np.argmax(eigvals.real)
    weights = eigvecs[:, principal_index].real
    # The principal eigenvector of a positive reciprocal matrix is always
    # single-signed in theory; abs() guards against a sign flip that's
    # purely a numerical-linear-algebra artifact, not a meaningful result.
    weights = np.abs(weights)
    return weights / weights.sum()


def compute_consistency_ratio(matrix: np.ndarray, weights: np.ndarray) -> dict:
    """Returns lambda_max (the matrix's principal eigenvalue), the
    Consistency Index (CI), and the Consistency Ratio (CR = CI / RI). A
    perfectly consistent matrix has lambda_max == n and CR == 0."""
    n = matrix.shape[0]
    # lambda_max = mean of (M @ w) / w, element-wise — the standard AHP
    # consistency check, algebraically equivalent to the Rayleigh quotient
    # for the principal eigenvector.
    weighted_sum = matrix @ weights
    lambda_max = float(np.mean(weighted_sum / weights))
    consistency_index = (lambda_max - n) / (n - 1) if n > 1 else 0.0
    random_index = RANDOM_INDEX.get(n)
    if random_index is None:
        raise ValueError(f"No published Random Index for {n} criteria (only 1-10 supported)")
    consistency_ratio = consistency_index / random_index if random_index > 0 else 0.0
    return {
        "lambda_max": lambda_max,
        "consistency_index": consistency_index,
        "consistency_ratio": consistency_ratio,
        "is_consistent": consistency_ratio <= CONSISTENCY_RATIO_THRESHOLD,
    }


def derive_weights_from_config(path: str) -> dict:
    """End-to-end: load a pairwise comparison config, build the matrix,
    derive weights, and check consistency. Returns a dict with `weights`
    (criterion -> weight), `matrix`, `criteria`, and the consistency-check
    fields from compute_consistency_ratio()."""
    config = load_ahp_config(path)
    matrix, criteria = build_comparison_matrix(config)
    weights = compute_ahp_weights(matrix)
    consistency = compute_consistency_ratio(matrix, weights)
    return {
        "weights": dict(zip(criteria, weights)),
        "matrix": matrix,
        "criteria": criteria,
        **consistency,
    }


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    result = derive_weights_from_config("config/ahp_pairwise_comparisons.yaml")
    for criterion, weight in result["weights"].items():
        print(f"{criterion}: {weight:.3f}")
    print(f"Consistency Ratio: {result['consistency_ratio']:.4f} "
          f"({'consistent' if result['is_consistent'] else 'INCONSISTENT — revisit the judgments'})")
