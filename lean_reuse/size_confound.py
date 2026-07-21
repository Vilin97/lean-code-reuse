"""Size-confounding audit and size-adjusted metric layer.

Motivation: several dashboard metrics (the amortization exponent, dependency
depth, degree, concentration) grow with repo size, so their raw cross-corpus
values partly measure size rather than quality. This module

  1. quantifies each metric's Spearman correlation with log10(decls),
  2. produces a *size-adjusted* value for every metric — the rank-residual after
     regressing the metric's rank on the size rank, z-scored — but ONLY when the
     adjustment actually reduces the size correlation (metrics already
     uncorrelated with size are kept as-is; residualizing tie-heavy metrics such
     as the sorry rate would otherwise inject spurious correlation), and
  3. records, per metric, the raw and adjusted correlation so the dashboard can
     prove ρ(size) ≈ 0 after adjustment.

Everything is keyed off `results_env.json` (the metrics JSON), so it needs no
Lean rebuild.
"""
from __future__ import annotations

import math

import numpy as np

# metric battery: (id, module.path, higher_is_better, adjustable)
# `adjustable=False` marks fields that are size descriptors or distributions,
# never point-scored (kept raw regardless).
BATTERY = [
    ("m3_crossdir", "cross_file.pct_edges_cross_dir", True),
    ("m3_outside", "cross_file.pct_decls_used_outside_file", True),
    ("m9_whole_ml", "import_graph.pct_files_importing_all_mathlib", False),
    ("m10_doc", "doc_coverage.pct_defs_with_doc", True),
    ("m10_comment", "doc_coverage.comment_density", True),
    ("m8_sorry", "proof_economy.sorry_rate", False),
    ("m7_dup", "duplication.body_dup_rate", False),
    ("m15_triv_stmt", "triviality.pct_trivial_statements", False),
    ("m15_triv_proof", "triviality.pct_trivial_proofs", False),
    ("m12_axioms", "trust_base.axioms_per_1k_decls", False),
    ("m2_stmt_share", "statement_vs_proof.share_signature", False),
    ("m5_top1", "concentration.top1pct_share", True),
    ("m1_mean_indeg", "reuse_degree.degree.mean", True),
    ("m1_ge2", "reuse_degree.pct_reused_ge2", True),
    ("m1_never", "reuse_degree.pct_never_reused", False),
    ("m6_maxd", "dependency_depth.max_depth", True),
    ("m6_meand", "dependency_depth.mean_depth", True),
    ("m14_amort_mean", "amortization.mean_log10_cost", True),
    ("m14_amort_p90", "amortization.p90_log10_cost", True),
    ("m4_ext_int", "external_reuse.external_internal_ratio", True),
    ("m11_branch", "complexity.branch_per_proof", True),
    ("m13_elab", "elab_cost.secs_per_kloc", True),
    ("m8_proof_med", "proof_economy.proof_lines.median", False),
    ("m9_file_med", "import_graph.median_file_loc", False),
    ("m4_ext_refs", "external_reuse.external_refs_per_decl", True),
    ("m4_vocab1k", "external_reuse.mathlib_vocab_per_1k_refs", True),
]


def _get(d, path):
    cur = d
    for p in path.split("."):
        cur = cur.get(p) if isinstance(cur, dict) else None
        if cur is None:
            return None
    return cur


def _rankdata(a):
    a = np.asarray(a, float)
    _, inv, cnt = np.unique(a, return_inverse=True, return_counts=True)
    order = np.argsort(a, kind="mergesort")
    r = np.empty(len(a))
    r[order] = np.arange(len(a))
    sums = np.zeros(len(cnt))
    np.add.at(sums, inv, r)
    return (sums / cnt)[inv]


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ra = _rankdata(a) - (len(a) - 1) / 2
    rb = _rankdata(b) - (len(b) - 1) / 2
    d = math.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / d) if d else 0.0


def _rank_resid_z(vals, size):
    """Rank-residual of vals on size, z-scored (Spearman(resid,size) ~ 0)."""
    rm = _rankdata(vals)
    rs = _rankdata(size)
    A = np.vstack([rs, np.ones_like(rs)]).T
    m, b = np.linalg.lstsq(A, rm, rcond=None)[0]
    res = rm - (m * rs + b)
    sd = res.std() or 1.0
    return res / sd


def compute(env_results, keys, size_key="decls"):
    """Return the size-confounding payload for the given repo keys.

    env_results: dict key -> {"meta": {...}, "metrics": {...}}
    keys:        ordered list of repo keys to include
    """
    keys = [k for k in keys if k in env_results]
    size = {k: env_results[k]["meta"][size_key] for k in keys}
    log_size = {k: math.log10(max(size[k], 1)) for k in keys}

    metrics_out = {}   # id -> {raw:{k:v}, adj:{k:v}, rho_raw, rho_adj, adjusted:bool, path, hib}
    for mid, path, hib in BATTERY:
        vk = {k: _get(env_results[k]["metrics"], path) for k in keys}
        kk = [k for k in keys if vk[k] is not None]
        if len(kk) < 8:
            continue
        vals = [vk[k] for k in kk]
        szs = [log_size[k] for k in kk]
        rho_raw = spearman(vals, szs)
        z = _rank_resid_z(vals, szs)
        adj_by_k = {k: float(z[i]) for i, k in enumerate(kk)}
        rho_adj_candidate = spearman([adj_by_k[k] for k in kk], szs)
        # only adopt the adjustment when it genuinely lowers |rho(size)|
        if abs(rho_adj_candidate) < abs(rho_raw) - 1e-9:
            adjusted = True
            final = adj_by_k
            rho_final = rho_adj_candidate
        else:
            adjusted = False
            final = {k: float(vk[k]) for k in kk}
            rho_final = rho_raw
        metrics_out[mid] = {
            "path": path, "hib": hib,
            "raw": {k: float(vk[k]) for k in kk},
            "adj": final,
            "rho_raw": round(rho_raw, 3),
            "rho_adj": round(rho_final, 3),
            "adjusted": adjusted,
        }

    max_abs_adj = max((abs(m["rho_adj"]) for m in metrics_out.values()), default=0.0)
    return {
        "size_key": size_key,
        "log_size": {k: round(log_size[k], 3) for k in keys},
        "size": {k: size[k] for k in keys},
        "metrics": metrics_out,
        "max_abs_rho_adj": round(max_abs_adj, 3),
        "n_adjusted": sum(1 for m in metrics_out.values() if m["adjusted"]),
        "n_total": len(metrics_out),
    }
