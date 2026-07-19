"""Metric registry and shared preparation for repo-graph metrics.

Each metric module exposes `NAME` and `compute(data, prep, ctx) -> dict`.
`data` is the repo cache dict, `prep` a Prep with numpy views and shared
derived arrays, `ctx` carries dependency name maps.
"""

from __future__ import annotations

import numpy as np

from ..parser import DECL_KINDS, TARGET_KINDS, THEOREM_LIKE

KIND_IDX = {k: i for i, k in enumerate(DECL_KINDS)}
TARGET_KIND_IDS = np.array(sorted(KIND_IDX[k] for k in TARGET_KINDS))
THEOREM_KIND_IDS = np.array(sorted(KIND_IDX[k] for k in THEOREM_LIKE if k != "example"))
DEF_KIND_IDS = np.array(sorted(KIND_IDX[k] for k in ("def", "abbrev", "structure", "class", "inductive")))

MODULES = [
    "reuse_degree",
    "statement_vs_proof",
    "cross_file",
    "external_reuse",
    "concentration",
    "dependency_depth",
    "duplication",
    "proof_economy",
    "import_graph",
    "doc_coverage",
    "complexity",
    "trust_base",
    "elab_cost",
    "amortization",
]


def _np(a, dtype):
    if len(a) == 0:
        return np.zeros(0, dtype=dtype)
    return np.frombuffer(a, dtype=dtype)


class Prep:
    def __init__(self, data: dict):
        d = data["decls"]
        e = data["edges"]
        self.n = len(d["name"])
        self.names = d["name"]
        self.kind = _np(d["kind"], np.int8)
        self.file = _np(d["file"], np.int32)
        self.anonymous = _np(d["anonymous"], np.int8).astype(bool)
        self.private = _np(d["private"], np.int8).astype(bool)
        self.has_doc = _np(d["has_doc"], np.int8).astype(bool) if "has_doc" in d else np.zeros(self.n, bool)
        self.branch = _np(d["branch"], np.int32) if "branch" in d else np.zeros(self.n, np.int32)
        self.sorry = _np(d["sorry"], np.int32)
        self.proof_lines = _np(d["proof_lines"], np.int32)
        self.sig_lines = _np(d["sig_lines"], np.int32) if "sig_lines" in d else np.zeros(self.n, np.int32)
        self.value_lines = _np(d["value_lines"], np.int32)
        self.sig_chars = _np(d["sig_chars"], np.int32)
        self.proof_chars = _np(d["proof_chars"], np.int32)
        self.sig_hash = _np(d["sig_hash"], np.int64)
        self.body_hash = _np(d["body_hash"], np.int64)
        self.body_len = _np(d["body_len"], np.int32)

        self.e_src = _np(e["src"], np.int32)
        self.e_repo = _np(e["dst_repo"], np.int8)
        self.e_dst = _np(e["dst"], np.int32)
        self.e_ctx = _np(e["ctx"], np.int8)
        self.e_cnt = _np(e["cnt"], np.int32)

        internal = self.e_repo == 0
        self.i_src = self.e_src[internal]
        self.i_dst = self.e_dst[internal]
        self.i_ctx = self.e_ctx[internal]
        self.i_cnt = self.e_cnt[internal]

        # distinct (src,dst) pairs, any context
        key = self.i_src.astype(np.int64) << 32 | self.i_dst.astype(np.int64)
        ukey = np.unique(key)
        self.p_src = (ukey >> 32).astype(np.int32)
        self.p_dst = (ukey & 0xFFFFFFFF).astype(np.int32)

        # distinct users per target, overall and per context
        self.indeg = np.bincount(self.p_dst, minlength=self.n) if self.n else np.zeros(0, int)
        self.indeg_ctx = []
        for c in (0, 1, 2):
            m = self.i_ctx == c
            k2 = np.unique(self.i_src[m].astype(np.int64) << 32 | self.i_dst[m].astype(np.int64))
            dsts = (k2 & 0xFFFFFFFF).astype(np.int32)
            self.indeg_ctx.append(np.bincount(dsts, minlength=self.n) if self.n else np.zeros(0, int))

        self.is_target = np.isin(self.kind, TARGET_KIND_IDS) & ~self.anonymous
        self.is_theorem = np.isin(self.kind, THEOREM_KIND_IDS) & ~self.anonymous
        self.is_def = np.isin(self.kind, DEF_KIND_IDS) & ~self.anonymous


def gini(x: np.ndarray) -> float:
    if len(x) == 0:
        return 0.0
    x = np.sort(x.astype(np.float64))
    s = x.sum()
    if s == 0:
        return 0.0
    n = len(x)
    cum = np.cumsum(x)
    return float((n + 1 - 2 * (cum / s).sum()) / n)


def ccdf(x: np.ndarray, thresholds) -> dict:
    n = max(1, len(x))
    return {str(t): round(float((x >= t).sum()) / n, 5) for t in thresholds}


def stats_summary(x: np.ndarray) -> dict:
    if len(x) == 0:
        return {"mean": 0, "median": 0, "p90": 0, "p99": 0, "max": 0}
    return {
        "mean": round(float(x.mean()), 3),
        "median": float(np.median(x)),
        "p90": float(np.percentile(x, 90)),
        "p99": float(np.percentile(x, 99)),
        "max": int(x.max()),
    }
