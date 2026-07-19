"""M8 — Proof economy and hygiene.

Short proofs that lean on many prior lemmas indicate a well-factored library;
long self-contained proofs indicate reinvention. Also counts `sorry`s
(incomplete proofs) — a direct quality red flag.
"""

from __future__ import annotations

import numpy as np

from . import stats_summary, KIND_IDX

NAME = "proof_economy"


def compute(data, prep, ctx) -> dict:
    thm = prep.is_theorem
    pl = prep.proof_lines[thm]
    has_proof = pl > 0

    # proof-context references (internal + external), occurrence-weighted, per source decl
    m = prep.e_ctx == 2
    proof_refs = np.bincount(prep.e_src[m], weights=prep.e_cnt[m], minlength=prep.n)
    pr = proof_refs[thm]

    total_proof_lines = int(pl.sum())
    total_proof_refs = int(pr.sum())

    sorry_thm = (prep.sorry[thm] > 0)
    n_examples = int((prep.kind == KIND_IDX["example"]).sum())

    sig_th = prep.sig_chars[thm]
    sl = prep.sig_lines[thm]
    sl = sl[sl > 0]
    return {
        "stmt_lines": stats_summary(sl) if len(sl) else None,
        "stmt_chars_median": float(np.median(sig_th)) if len(sig_th) else None,
        "n_theorems": int(thm.sum()),
        "proof_lines": stats_summary(pl[has_proof]) if has_proof.any() else stats_summary(pl),
        "refs_per_proof": round(float(pr[has_proof].mean()), 3) if has_proof.any() else 0.0,
        "refs_per_proof_line": round(total_proof_refs / total_proof_lines, 3)
        if total_proof_lines
        else None,
        "sorry_rate": round(float(sorry_thm.mean()), 4) if len(sorry_thm) else 0.0,
        "n_sorried_theorems": int(sorry_thm.sum()),
        "n_examples": n_examples,
    }
