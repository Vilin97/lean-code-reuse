"""M16 — Architecture: intensive reuse-shape metrics.

Size-independent by construction where possible: how reuse is *organized*
(directory breadth, cross-directory wiring vs a random baseline) and what it
*targets* (definitions vs theorems), rather than how much of it there is.
These are the discriminant-valid signals behind the Architecture Index — a
large-but-unarchitected corpus scores low on them (lean-pool: 44k decls,
0.1% cross-directory reuse), which is the test that separates genuine
architecture signals from size proxies. See lean_reuse/architecture_index.py.

Directory = first two path components of the source file. NOTE: for a file
at depth 2 ("PFR/Basic.lean") the bucket includes the filename, so every
such file is its own singleton bucket — cross-directory reduces to
cross-file for flat repo layouts. This matches the R&D scripts these
numbers were validated against (slightly stricter than cross_file._dir_of);
keep it for reproducibility.
"""

from __future__ import annotations

import math

import numpy as np

from ..parser import DECL_KINDS

NAME = "architecture"

_KIND = {k: i for i, k in enumerate(DECL_KINDS)}
# reuse *targets* counted as definitions: the abstraction-bearing kinds.
# The exact tier only emits theorem/def/instance/inductive/axiom/opaque
# (elaboration folds lemma->theorem, abbrev/structure/class->def/inductive);
# the extra kinds here make the same split correct on textual-tier caches,
# which keep those surface kinds distinct.
DEF_KINDS = np.array(sorted(_KIND[k] for k in
                            ("def", "abbrev", "structure", "class", "instance",
                             "inductive", "axiom", "opaque")))
THM_KINDS = np.array(sorted(_KIND[k] for k in ("theorem", "lemma", "proof_wanted")))


def _mann_whitney_auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """P(random pos > random neg), ties at 0.5 — rank-based Mann-Whitney AUC."""
    if len(pos) == 0 or len(neg) == 0:
        return 0.5
    allv = np.concatenate([pos, neg])
    order = np.argsort(allv, kind="mergesort")
    ranks = np.empty(len(allv))
    ranks[order] = np.arange(1, len(allv) + 1)
    _, inv, cnt = np.unique(allv, return_inverse=True, return_counts=True)
    csum = np.zeros(len(cnt))
    np.add.at(csum, inv, ranks)
    avg = (csum / cnt)[inv]
    r1 = avg[: len(pos)].sum()
    return float((r1 - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def compute(data, prep, ctx) -> dict:
    n = prep.n
    kind = prep.kind
    indeg = prep.indeg
    is_def = np.isin(kind, DEF_KINDS)
    is_thm = np.isin(kind, THM_KINDS)
    reusable = is_def | is_thm

    out = {
        "dir_breadth_mean": 0.0,
        "crossdir_vs_random": 0.0,
        "modularity_q": 0.0,
        "def_thm_indeg_ratio": 0.0,
        "def_reuse_auc": 0.5,
        "hub_def_share": 0.0,
        "reuse_entropy": 0.0,
    }

    # --- definitions-are-hubs family (needs decls only) ---------------------
    if reusable.any():
        md = indeg[is_def].mean() if is_def.any() else 0.0
        mt = indeg[is_thm].mean() if is_thm.any() else 0.0
        out["def_thm_indeg_ratio"] = round(float(md / mt), 6) if mt > 0 else 0.0
        ridx = np.where(reusable)[0]
        out["def_reuse_auc"] = round(
            _mann_whitney_auc(indeg[ridx[is_def[ridx]]].astype(float),
                              indeg[ridx[is_thm[ridx]]].astype(float)), 6)
        order = ridx[np.argsort(indeg[ridx])[::-1]]
        k5 = max(1, int(0.05 * len(ridx)))
        out["hub_def_share"] = round(float(is_def[order[:k5]].mean()), 6)
        idr = indeg[reusable].astype(np.float64)
        idr = idr[idr > 0]
        if len(idr) > 1 and idr.sum() > 0:
            p = idr / idr.sum()
            out["reuse_entropy"] = round(float(-(p * np.log(p)).sum() / math.log(len(idr))), 6)

    # --- directory wiring (needs internal edges) ----------------------------
    if len(prep.p_src) == 0:
        return out
    dirs = np.array(["/".join(f.split("/")[:2]) for f in data["files"]])
    _, dcode = np.unique(dirs, return_inverse=True)
    k_dirs = dcode.max() + 1
    srcd = dcode[prep.file[prep.p_src]]
    dstd = dcode[prep.file[prep.p_dst]]
    n_edges = len(srcd)

    # generality: distinct user-directories per reused declaration
    pair = np.unique(prep.p_dst.astype(np.int64) << 32 | srcd.astype(np.int64))
    breadth = np.bincount((pair >> 32).astype(np.int64), minlength=n)
    br = breadth[breadth > 0]
    out["dir_breadth_mean"] = round(float(br.mean()), 6) if len(br) else 0.0

    if k_dirs > 1:
        # each edge contributes one endpoint to each of its two directories
        a = (np.bincount(srcd, minlength=k_dirs) + np.bincount(dstd, minlength=k_dirs)).astype(np.float64)
        intra = np.bincount(srcd[srcd == dstd], minlength=k_dirs).astype(np.float64)
        halves = (a / (2 * n_edges)) ** 2
        out["modularity_q"] = round(float((intra / n_edges - halves).sum()), 6)
        exp_cross = 1.0 - halves.sum()
        act_cross = float((srcd != dstd).mean())
        out["crossdir_vs_random"] = round(act_cross / exp_cross, 6) if exp_cross > 0 else 0.0
    return out
