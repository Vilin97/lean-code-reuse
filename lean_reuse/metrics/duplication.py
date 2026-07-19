"""M7 — Duplication (the inverse of reuse).

Exact-duplicate rate of whitespace-normalized declaration bodies, and of
theorem statements. Copy-pasted proofs and restated lemmas are the failure
mode reuse metrics should punish; AI-generated corpora are prone to both.
"""

from __future__ import annotations

import numpy as np

NAME = "duplication"

MIN_BODY = 60   # chars, normalized — ignore trivial bodies like `rfl`
MIN_SIG = 40


def _dup(hashes: np.ndarray) -> dict:
    n = len(hashes)
    if n == 0:
        return {"n": 0, "dup_rate": 0.0, "max_cluster": 0}
    _, counts = np.unique(hashes, return_counts=True)
    return {
        "n": int(n),
        "dup_rate": round(float(n - len(counts)) / n, 4),
        "max_cluster": int(counts.max()),
    }


def compute(data, prep, ctx) -> dict:
    named = ~prep.anonymous
    body_mask = named & (prep.body_len >= MIN_BODY)
    sig_mask = prep.is_theorem & (prep.sig_chars >= MIN_SIG)
    body = _dup(prep.body_hash[body_mask])
    sig = _dup(prep.sig_hash[sig_mask])
    return {
        "body_dup_rate": body["dup_rate"],
        "body_dup_n": body["n"],
        "body_max_cluster": body["max_cluster"],
        "stmt_dup_rate": sig["dup_rate"],
        "stmt_dup_n": sig["n"],
        "stmt_max_cluster": sig["max_cluster"],
    }
