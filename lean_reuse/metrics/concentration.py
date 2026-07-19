"""M5 — Reuse concentration.

How evenly is reuse spread? Gini coefficient of the internal reuse-degree
distribution plus the share of all internal references absorbed by the top
1% / 10% most-reused declarations. Extreme concentration (a handful of hub
decls, everything else dead) and zero concentration (nothing reused) are both
unhealthy; mature libraries sit in a characteristic band.
"""

from __future__ import annotations

import numpy as np

from . import gini

NAME = "concentration"


def compute(data, prep, ctx) -> dict:
    deg = prep.indeg[prep.is_target].astype(np.int64)
    total = int(deg.sum())
    if total == 0 or len(deg) == 0:
        return {"gini": None, "top1pct_share": None, "top10pct_share": None}
    s = np.sort(deg)[::-1]
    n = len(s)
    k1 = max(1, n // 100)
    k10 = max(1, n // 10)
    return {
        "gini": round(gini(deg), 4),
        "top1pct_share": round(float(s[:k1].sum()) / total, 4),
        "top10pct_share": round(float(s[:k10].sum()) / total, 4),
    }
