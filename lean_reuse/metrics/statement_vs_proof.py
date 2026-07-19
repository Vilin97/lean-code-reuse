"""M2 — Statement vs proof reuse.

Where do references live? Signature (statement/type) references and
definition-value references are load-bearing: they shape the API. Proof
references are erasable. A healthy library has substantial statement-level
reuse (definitions building on definitions), not just proofs quoting lemmas.
Also splits reuse by target kind: are theorems being reused, or only defs?
"""

from __future__ import annotations

import numpy as np

NAME = "statement_vs_proof"


def compute(data, prep, ctx) -> dict:
    # context shares over ALL references (internal + external), occurrence-weighted
    tot = np.zeros(3, dtype=np.int64)
    for c in (0, 1, 2):
        tot[c] = int(prep.e_cnt[prep.e_ctx == c].sum())
    total = int(tot.sum())
    shares = (tot / total).round(4).tolist() if total else [0, 0, 0]

    # internal reuse of targets, split by context of use
    t = prep.is_target
    sig_deg = prep.indeg_ctx[0][t]
    val_deg = prep.indeg_ctx[1][t]
    prf_deg = prep.indeg_ctx[2][t]

    # internal references landing on theorems vs defs (occurrence-weighted)
    thm_refs = int(prep.i_cnt[prep.is_theorem[prep.i_dst]].sum())
    def_refs = int(prep.i_cnt[prep.is_def[prep.i_dst]].sum())

    # theorems reused inside other *statements* (a sign of layered theory)
    thm = prep.is_theorem
    thm_stmt_reuse = float((prep.indeg_ctx[0][thm] > 0).mean()) if thm.any() else 0.0

    return {
        "share_signature": shares[0],
        "share_value": shares[1],
        "share_proof": shares[2],
        "load_bearing_share": round(shares[0] + shares[1], 4),
        "mean_stmt_indeg": round(float((sig_deg + val_deg).mean()) if len(sig_deg) else 0.0, 3),
        "mean_proof_indeg": round(float(prf_deg.mean()) if len(prf_deg) else 0.0, 3),
        "internal_refs_to_theorems": thm_refs,
        "internal_refs_to_defs": def_refs,
        "thm_def_ref_ratio": round(thm_refs / def_refs, 3) if def_refs else None,
        "pct_theorems_used_in_statements": round(thm_stmt_reuse, 4),
    }
