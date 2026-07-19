"""M14 — Proof amortization (reuse as compression).

The graph-theoretic answer to "reuse must matter": measure how much work the
library *avoids redoing* through sharing. For each declaration define its
fully-inlined cost

    cost(v) = 1 + sum over internal deps u of cost(u)   (with repetition)

— the size of the dependency tree if nothing were ever shared: every lemma
re-proved at every use site. In a flat corpus cost ≈ chain length; in a
deeply shared library it grows exponentially (Mathlib's costs overflow any
integer, so everything is computed in log-space). Reported as orders of
magnitude: L(v) = log10 cost(v). A mean L of 30 means the average
declaration sits on a dependency tree that sharing compresses by thirty
orders of magnitude — reuse measured as compression, in the
minimum-description-length sense.

Declarations stuck in (residual) cycles are excluded; their share is
reported by M6.
"""

from __future__ import annotations

from collections import deque

import numpy as np

NAME = "amortization"

LN10 = np.log(10.0)


def compute(data, prep, ctx) -> dict:
    n = prep.n
    src, dst = prep.p_src, prep.p_dst
    if n == 0 or len(src) == 0:
        return {"mean_log10_cost": 0.0, "median_log10_cost": 0.0,
                "max_log10_cost": 0.0, "total_amortization_exp": 0.0}

    # topological peel identical to dependency_depth: process a node once all
    # of its dependencies (outgoing edges) are resolved
    outdeg = np.bincount(src, minlength=n).astype(np.int64)
    order = np.argsort(dst, kind="stable")
    rs = src[order]
    rd = dst[order]
    starts = np.searchsorted(rd, np.arange(n + 1))

    # forward adjacency (deps of each node) for cost accumulation
    order2 = np.argsort(src, kind="stable")
    fs = src[order2]
    fd = dst[order2]
    fstarts = np.searchsorted(fs, np.arange(n + 1))

    logcost = np.zeros(n)  # natural-log of cost; leaves: log(1) = 0
    done = np.zeros(n, dtype=bool)
    out_l = outdeg.tolist()
    q = deque(np.where(outdeg == 0)[0].tolist())
    rs_l = rs.tolist()
    starts_l = starts.tolist()
    while q:
        v = q.popleft()
        deps = fd[fstarts[v]:fstarts[v + 1]]
        if len(deps):
            dl = logcost[deps]
            m = dl.max()
            # cost(v) = 1 + sum(exp(dl)) computed stably in log space
            logcost[v] = m + np.log(np.exp(-m) + np.exp(dl - m).sum())
        done[v] = True
        for i in range(starts_l[v], starts_l[v + 1]):
            s = rs_l[i]
            out_l[s] -= 1
            if out_l[s] == 0:
                q.append(s)

    L = logcost[done] / LN10  # log10
    t_mask = done & prep.is_theorem
    Lt = logcost[t_mask] / LN10
    # total amortization exponent: log10(sum of expanded costs / n)
    m = logcost[done].max() if done.any() else 0.0
    total_log = (m + np.log(np.exp(logcost[done] - m).sum())) / LN10
    return {
        "mean_log10_cost": round(float(L.mean()), 2) if len(L) else 0.0,
        "median_log10_cost": round(float(np.median(L)), 2) if len(L) else 0.0,
        "p90_log10_cost": round(float(np.percentile(L, 90)), 2) if len(L) else 0.0,
        "max_log10_cost": round(float(L.max()), 2) if len(L) else 0.0,
        "mean_log10_cost_theorems": round(float(Lt.mean()), 2) if len(Lt) else None,
        "total_amortization_exp": round(float(total_log - np.log10(max(1, done.sum()))), 2),
        "n_scored": int(done.sum()),
    }
