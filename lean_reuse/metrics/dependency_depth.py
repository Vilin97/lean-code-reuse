"""M6 — Internal dependency depth.

Longest chain of declarations each building on the previous, within the repo.
Deep chains = layered theory (definitions on definitions, lemmas on lemmas);
a flat repo (depth ~2-3) is a bag of independent facts, not a library.
Computed by topological peeling; declarations stuck in (textual) cycles are
reported separately.
"""

from __future__ import annotations

import numpy as np

NAME = "dependency_depth"


def compute(data, prep, ctx) -> dict:
    n = prep.n
    src, dst = prep.p_src, prep.p_dst
    if n == 0 or len(src) == 0:
        return {"max_depth": 0, "mean_depth": 0.0, "pct_in_cycles": 0.0}

    outdeg = np.bincount(src, minlength=n).astype(np.int64)
    # reverse adjacency: for each dst, the list of srcs — via sort by dst
    order = np.argsort(dst, kind="stable")
    rs = src[order]
    rd = dst[order]
    starts = np.searchsorted(rd, np.arange(n + 1))

    depth = np.ones(n, dtype=np.int32)
    from collections import deque

    q = deque(np.where(outdeg == 0)[0].tolist())
    processed = 0
    outdeg_l = outdeg  # mutate in place
    rs_l = rs.tolist()
    depth_l = depth.tolist()
    starts_l = starts.tolist()
    out_l = outdeg_l.tolist()
    while q:
        v = q.popleft()
        processed += 1
        dv = depth_l[v]
        for i in range(starts_l[v], starts_l[v + 1]):
            s = rs_l[i]
            if depth_l[s] <= dv:
                depth_l[s] = dv + 1
            out_l[s] -= 1
            if out_l[s] == 0:
                q.append(s)
    depth = np.array(depth_l)
    done = np.array(out_l) == 0
    d_ok = depth[done]
    return {
        "max_depth": int(d_ok.max()) if done.any() else 0,
        "mean_depth": round(float(d_ok.mean()), 3) if done.any() else 0.0,
        "p90_depth": float(np.percentile(d_ok, 90)) if done.any() else 0.0,
        "pct_in_cycles": round(float((~done).mean()), 4),
    }
