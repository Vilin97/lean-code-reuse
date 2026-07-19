"""Compare textual vs env tiers on repos where both exist.

Per repo: join named target decls by fully-qualified name, correlate internal
in-degrees, and compare headline metrics. Output JSON for the report.
"""

from __future__ import annotations

import argparse
import json
import os
import pickle

import numpy as np

from .metrics import Prep


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = np.argsort(np.argsort(a, kind="stable")).astype(float)
    rb = np.argsort(np.argsort(b, kind="stable")).astype(float)
    # average ties via ranking on sorted values
    def rank_avg(x):
        order = np.argsort(x, kind="stable")
        ranks = np.empty(len(x))
        sx = x[order]
        i = 0
        while i < len(x):
            j = i
            while j + 1 < len(x) and sx[j + 1] == sx[i]:
                j += 1
            ranks[order[i : j + 1]] = (i + j) / 2.0
            i = j + 1
        return ranks

    ra, rb = rank_avg(a.astype(float)), rank_avg(b.astype(float))
    ca, cb = ra - ra.mean(), rb - rb.mean()
    denom = np.sqrt((ca**2).sum() * (cb**2).sum())
    return float((ca * cb).sum() / denom) if denom else 0.0


def compare(tx_path: str, env_path: str) -> dict:
    with open(tx_path, "rb") as f:
        te = pickle.load(f)
    with open(env_path, "rb") as f:
        en = pickle.load(f)
    pt, pe = Prep(te), Prep(en)
    tidx = {nm: i for i, nm in enumerate(te["decls"]["name"]) if pt.is_target[i]}
    pairs = [
        (tidx[nm], j)
        for j, nm in enumerate(en["decls"]["name"])
        if pe.is_target[j] and nm in tidx
    ]
    if not pairs:
        return {}
    ti = np.array([a for a, _ in pairs])
    ei = np.array([b for _, b in pairs])
    dt = pt.indeg[ti].astype(np.int64)
    de = pe.indeg[ei].astype(np.int64)
    return {
        "n_joined": len(pairs),
        "join_rate_env": round(len(pairs) / int(pe.is_target.sum()), 4),
        "spearman_indeg": round(spearman(dt, de), 3),
        "pearson_log1p": round(float(np.corrcoef(np.log1p(dt), np.log1p(de))[0, 1]), 3),
        "never_textual": round(float((dt == 0).mean()), 4),
        "never_env": round(float((de == 0).mean()), 4),
        "mean_deg_textual": round(float(dt.mean()), 3),
        "mean_deg_env": round(float(de.mean()), 3),
        "textual_zero_env_nonzero": round(float(((dt == 0) & (de > 0)).mean()), 4),
        "env_zero_textual_nonzero": round(float(((dt > 0) & (de == 0)).mean()), 4),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--textual-cache-dir", required=True)
    ap.add_argument("--env-cache-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = {}
    for fn in sorted(os.listdir(args.env_cache_dir)):
        if not fn.endswith(".pkl"):
            continue
        key = fn[:-4]
        tx = os.path.join(args.textual_cache_dir, fn)
        if not os.path.exists(tx):
            continue
        print(f"[validate] {key}", flush=True)
        out[key] = compare(tx, os.path.join(args.env_cache_dir, fn))
    with open(args.out, "w") as f:
        json.dump(out, f, indent=1)
    print(f"[validate] wrote {args.out}")


if __name__ == "__main__":
    main()
