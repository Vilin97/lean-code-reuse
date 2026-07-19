"""Build graphs and compute every metric for every registered repo.

Usage:
    python -m lean_reuse.run_all --repos-dir <dir with checkouts> \
        --cache-dir <cache dir> --out results.json [--only k1,k2] [--force]
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import pickle

from .graphbuild import build_all
from .metrics import MODULES, Prep
from .repos import BUILD_ORDER, REPOS


def compute_metrics(cache_dir: str, keys: list[str], bench: dict | None = None) -> dict:
    results: dict = {}
    # id->name maps for upstream repos, loaded once, shared via ctx
    dep_names: dict[str, dict[int, str]] = {}

    def load_cache(k: str) -> dict:
        with open(os.path.join(cache_dir, k + ".pkl"), "rb") as f:
            return pickle.load(f)

    for k in keys:
        data = load_cache(k)
        if "dep_names" not in data:
            for dk in REPOS[k]["deps"]:
                if dk not in dep_names:
                    try:
                        t = load_cache(dk)["table"]
                    except FileNotFoundError:
                        continue
                    dep_names[dk] = {v: nm for nm, v in t.items()}
        prep = Prep(data)
        ctx = {"dep_names": dep_names, "bench": bench or {}}
        metrics = {}
        for mod_name in MODULES:
            mod = importlib.import_module(f".metrics.{mod_name}", __package__)
            metrics[mod.NAME] = mod.compute(data, prep, ctx)
        s = data["stats"]
        results[k] = {
            "meta": {
                "tier": data.get("tier", "textual"),
                "join_rate": s.get("join_rate"),
                "label": data["label"],
                "category": data["category"],
                "provenance": data["provenance"],
                "stars": data["stars"],
                "url": data["url"],
                "files": s["n_files"],
                "loc": s["loc"],
                "decls": s["n_decls"],
                "edges": s["n_edges"],
                "dotted_coverage": round(s["dotted_resolved"] / max(1, s["dotted_tokens"]), 4),
                "parse_errors": s["n_parse_errors"],
            },
            "metrics": metrics,
        }
        print(f"[metrics] {k} done", flush=True)
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos-dir", required=True)
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--nproc", type=int, default=8)
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument("--bench", default="")
    args = ap.parse_args()

    only = set(args.only.split(",")) if args.only else None
    if not args.skip_build:
        build_all(args.repos_dir, args.cache_dir, only=only, force=args.force, nproc=args.nproc)

    keys = [k for k in BUILD_ORDER if not only or k in only]
    keys = [k for k in keys if os.path.exists(os.path.join(args.cache_dir, k + ".pkl"))]
    bench = None
    if args.bench and os.path.exists(args.bench):
        with open(args.bench) as f:
            bench = json.load(f)
    results = compute_metrics(args.cache_dir, keys, bench)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=1)
    print(f"[done] wrote {args.out}")


if __name__ == "__main__":
    main()
