"""M1 — Internal reuse degree.

For every reusable declaration (theorem/lemma/def/abbrev/structure/class/
inductive/axiom/opaque/alias; instances and anonymous decls excluded), count
how many *distinct* other declarations in the same repo reference it.
Reports the distribution: mean/median/tails, CCDF, and the share of
declarations never reused internally.
"""

from __future__ import annotations

import numpy as np

from . import ccdf, stats_summary

NAME = "reuse_degree"

CCDF_THRESHOLDS = [1, 2, 3, 5, 10, 20, 50, 100, 200, 500, 1000]


def compute(data, prep, ctx) -> dict:
    deg = prep.indeg[prep.is_target]
    n = len(deg)
    out = {
        "n_reusable_decls": int(n),
        "degree": stats_summary(deg),
        "pct_never_reused": round(float((deg == 0).mean()) if n else 0.0, 4),
        "pct_reused_ge2": round(float((deg >= 2).mean()) if n else 0.0, 4),
        "ccdf": ccdf(deg, CCDF_THRESHOLDS),
    }
    # top reused decls (for qualitative inspection)
    idx = np.where(prep.is_target)[0]
    if len(idx):
        top = idx[np.argsort(prep.indeg[idx])[::-1][:20]]
        out["top"] = [
            {"name": prep.names[i], "deg": int(prep.indeg[i])} for i in top if prep.indeg[i] > 0
        ]
    else:
        out["top"] = []
    return out
