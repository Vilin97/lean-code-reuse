"""The Architecture Index and the discriminant-validity test.

The question "is this metric just measuring repo size?" is NOT answered by
its correlation with size — a genuine quality signal can co-vary with size
because good libraries tend to grow. Residualizing such a metric on size
throws the signal away (the mistake this module corrects: it pushed Mathlib
to mid-pack on metrics where it genuinely leads). The correct test is
*discriminant validity*: does a large-but-uncurated corpus score high?

The control group is the three largest non-Mathlib corpora, none of them a
curated library (lean-pool 44k decls, erdos90 37k, ATLAS 16k). A metric is
a size proxy when they rank in its top half AND bigger repos genuinely
score better on it (amortization, depth, mean in-degree fail both ways —
the big-uncurated corpora's median beats the reviewed median purely from
bulk). A metric on which they rank near the bottom despite their bulk is
real architecture (cross-directory reuse: Mathlib 62% of edges, reviewed
median 17%, lean-pool 0.05% — an archipelago of 44k declarations scores
nothing). Size-independent floor metrics that big dumps happen to pass
(the sorry rate) are neither — they stay real signals; see
discriminant_verdict.

The Architecture Index averages the percentile ranks of the discriminant-
valid wiring metrics. The primary variant maximizes size-independence
(cross-directory reuse + directory breadth + cross-dir-vs-random baseline:
|rho_size| = 0.32, reviewed-vs-slop AUC = 0.93, Mathlib #1); the secondary
variant swaps directory breadth for the definitions-are-hubs ratio and
reaches AUC = 1.00 at |rho_size| = 0.43.

Everything is keyed off results_env.json; no Lean rebuild needed.
"""
from __future__ import annotations

import math

import numpy as np

from .size_confound import spearman

# quality anchors (same sets as the R&D scripts these numbers were validated
# against): community-reviewed libraries vs declared slop / proof dumps
REVIEWED = {"mathlib4", "flt", "pfr", "addcombi", "carleson", "pnt", "brownian", "cslib", "physlib"}
SLOP = {"seed-prover", "superhuman", "pedigree", "gblean", "atlas"}
# the large-but-uncurated control group for the discriminant test
BIG_UNCURATED = {"lean-pool", "atlas", "erdos90"}

# index components: (id, metric path). Higher is better for all of them.
INDEX_PRIMARY = [
    ("crossdir", "cross_file.pct_edges_cross_dir"),
    ("dir_breadth", "architecture.dir_breadth_mean"),
    ("crossdir_v_rand", "architecture.crossdir_vs_random"),
]
INDEX_MAX_SEPARATION = [
    ("crossdir", "cross_file.pct_edges_cross_dir"),
    ("def_hub_ratio", "architecture.def_thm_indeg_ratio"),
    ("crossdir_v_rand", "architecture.crossdir_vs_random"),
]

# headline rows for the size-proxy vs real-signal table:
# (id, label, metric path, higher_is_better, is_pct)
DISCRIMINANT_TABLE = [
    ("crossdir", "cross-directory reuse", "cross_file.pct_edges_cross_dir", True, True),
    ("dir_breadth", "directory breadth of reuse", "architecture.dir_breadth_mean", True, False),
    ("crossdir_v_rand", "cross-dir vs random baseline", "architecture.crossdir_vs_random", True, False),
    ("def_hub_ratio", "definitions-are-hubs ratio", "architecture.def_thm_indeg_ratio", True, False),
    ("outside_file", "used outside defining file", "cross_file.pct_decls_used_outside_file", True, True),
    ("amort", "amortization exponent", "amortization.mean_log10_cost", True, False),
    ("max_depth", "max dependency depth", "dependency_depth.max_depth", True, False),
    ("mean_indeg", "mean in-degree", "reuse_degree.degree.mean", True, False),
]


def _get(d, path):
    cur = d
    for p in path.split("."):
        cur = cur.get(p) if isinstance(cur, dict) else None
        if cur is None:
            return None
    return cur


def _pct_rank(vk: dict, hib: bool = True) -> dict:
    """Percentile rank in [0,1] over the given repo values, ties averaged."""
    sign = 1 if hib else -1
    items = [(k, v * sign) for k, v in vk.items() if v is not None]
    vals = [v for _, v in items]
    return {k: (sum(1 for o in vals if o < v) + 0.5 * sum(1 for o in vals if o == v)) / len(vals)
            for k, v in items}


def _auc(vk: dict, hib: bool = True) -> float:
    hi = [vk[k] for k in REVIEWED if vk.get(k) is not None]
    lo = [vk[k] for k in SLOP if vk.get(k) is not None]
    if not hi or not lo:
        return 0.5
    c = sum((h > l) + 0.5 * (h == l) for h in hi for l in lo) / (len(hi) * len(lo))
    return c if hib else 1 - c


def _oriented_ranks(vk: dict, hib: bool) -> dict:
    """Tie-averaged rank, 1 = best under the metric's own orientation.

    Ties MUST be averaged: several hygiene metrics have mass ties (15 repos
    share a 0.0 sorry rate), and ordinal ranking would make the verdict
    depend on the caller's key order rather than on the data.
    """
    sign = -1.0 if hib else 1.0
    ks = [k for k in vk if vk[k] is not None]
    vals = [sign * vk[k] for k in ks]
    order = np.argsort(vals, kind="mergesort")
    r = np.empty(len(ks))
    r[order] = np.arange(1, len(ks) + 1)
    _, inv, cnt = np.unique(vals, return_inverse=True, return_counts=True)
    sums = np.zeros(len(cnt))
    np.add.at(sums, inv, r)
    avg = (sums / cnt)[inv]
    return {k: float(avg[i]) for i, k in enumerate(ks)}


def discriminant_verdict(vk: dict, hib: bool, oriented_rho: float) -> tuple[bool, list[float]]:
    """(is_real_signal, big-uncurated tie-averaged oriented ranks).

    A metric is a SIZE PROXY when both hold: the big-uncurated corpora rank
    in its top half despite being uncurated (median oriented rank below
    ~44% of the field), AND bigger repos genuinely score better on it
    (oriented Spearman vs log-size >= +0.3). The second condition keeps
    size-independent floor metrics (the sorry rate: big dumps pass it, but
    not *because* they are big — rho ~ -0.08) from being mislabeled as
    size proxies. Everything else is a real signal.
    """
    ranks = _oriented_ranks(vk, hib)
    bb = sorted(round(ranks[k], 1) for k in BIG_UNCURATED if k in ranks)
    n = len(ranks)
    if not bb:
        return True, []
    proxy = float(np.median(bb)) < 0.44 * n and oriented_rho >= 0.3
    return not proxy, bb


def _index(env, keys, components):
    vk_of = {mid: {k: _get(env[k]["metrics"], path) for k in keys} for mid, path in components}
    pr = {mid: _pct_rank(vk) for mid, vk in vk_of.items()}
    # round away 1-ulp float-mean noise so genuinely tied index scores stay
    # tied for the rank-based rho below
    idx = {k: round(float(np.mean([pr[mid][k] for mid, _ in components if k in pr[mid]])), 10)
           for k in keys}
    logd = {k: math.log10(max(env[k]["meta"]["decls"], 1)) for k in keys}
    ranking = sorted(keys, key=lambda k: -idx[k])
    return {
        "components": [mid for mid, _ in components],
        "score": {k: round(idx[k] * 100, 1) for k in keys},
        "comp_pct": {k: {mid: round(pr[mid][k] * 100, 1) for mid, _ in components if k in pr[mid]}
                     for k in keys},
        "auc": round(_auc(idx), 3),
        "rho_size": round(spearman([idx[k] for k in keys], [logd[k] for k in keys]), 3),
        "ranking": ranking,
        "mathlib_rank": ranking.index("mathlib4") + 1 if "mathlib4" in keys else None,
        "big_uncurated_ranks": {k: ranking.index(k) + 1 for k in sorted(BIG_UNCURATED) if k in keys},
    }


def compute(env_results, keys):
    """Return the architecture-index payload for the given repo keys."""
    keys = [k for k in keys if k in env_results]
    logd = {k: math.log10(max(env_results[k]["meta"]["decls"], 1)) for k in keys}

    table = []
    for mid, label, path, hib, is_pct in DISCRIMINANT_TABLE:
        vk = {k: _get(env_results[k]["metrics"], path) for k in keys}
        kk = [k for k in keys if vk[k] is not None]
        if len(kk) < 8:
            continue
        rho = spearman([vk[k] for k in kk], [logd[k] for k in kk])
        real, bb_ranks = discriminant_verdict(vk, hib, rho if hib else -rho)
        rev = float(np.median([vk[k] for k in REVIEWED if vk.get(k) is not None]))
        bb = float(np.median([vk[k] for k in BIG_UNCURATED if vk.get(k) is not None]))
        table.append({
            "id": mid, "label": label, "pct": is_pct,
            "mathlib": vk.get("mathlib4"),
            "reviewed_med": round(rev, 3),
            "big_uncurated_med": round(bb, 3),
            "rho_size": round(rho, 2),
            "auc": round(_auc(vk, hib), 2),
            "big_uncurated_ranks": bb_ranks,
            "real_signal": real,
        })

    return {
        "primary": _index(env_results, keys, INDEX_PRIMARY),
        "max_separation": _index(env_results, keys, INDEX_MAX_SEPARATION),
        "table": table,
        "n_repos": len(keys),
    }


def classify_battery(env_results, keys, battery):
    """Discriminant verdict for an arbitrary battery of (mid, path, hib).

    Returns {mid: {"real_signal": bool, "big_uncurated_ranks": [...], "rho_size": float}}.
    """
    keys = [k for k in keys if k in env_results]
    logd = {k: math.log10(max(env_results[k]["meta"]["decls"], 1)) for k in keys}
    out = {}
    for mid, path, hib in battery:
        vk = {k: _get(env_results[k]["metrics"], path) for k in keys}
        kk = [k for k in keys if vk[k] is not None]
        if len(kk) < 8:
            continue
        rho = spearman([vk[k] for k in kk], [logd[k] for k in kk])
        real, bb_ranks = discriminant_verdict(vk, hib, rho if hib else -rho)
        out[mid] = {
            "real_signal": real,
            "big_uncurated_ranks": bb_ranks,
            "rho_size": round(rho, 3),
        }
    return out
