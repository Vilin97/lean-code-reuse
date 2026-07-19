"""Elaboration-cost benchmark (heartbeats-per-LOC proxy).

For each repo with a working build, sample N source files, re-elaborate each
with `lake env lean <file>` and time it. The import-loading cost is estimated
by timing a stub file containing only the sample's import header (cached per
distinct import set) and subtracted. Emits JSON: {repo: {secs_per_kloc, ...}}.

Usage:
    python -m lean_reuse.elab_bench --config bench_config.json --out bench.json
config: {repo_key: {"build_dir": path, "src_prefix": optional path prefix
         prepended to cache file paths}, ...}
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import random
import re
import subprocess
import time

ELAN_BIN = os.path.expanduser("~/.elan/bin")


def time_lean(build_dir: str, path: str, timeout: int) -> float | None:
    env = dict(os.environ)
    env["PATH"] = ELAN_BIN + ":" + env.get("PATH", "")
    t0 = time.time()
    try:
        cp = subprocess.run(
            ["lake", "env", "lean", path],
            cwd=build_dir, env=env, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None
    if cp.returncode != 0:
        return None
    return time.time() - t0


def bench_repo(key: str, cfg: dict, cache_dir: str, n_files: int, timeout: int,
               scratch: str, rng: random.Random) -> dict | None:
    with open(os.path.join(cache_dir, key + ".pkl"), "rb") as f:
        cache = pickle.load(f)
    files = cache["files"]
    loc = list(cache["file_loc"])
    build_dir = cfg["build_dir"]
    prefix = cfg.get("src_prefix", "")
    candidates = [
        (os.path.join(prefix, f) if prefix else f, loc[i])
        for i, f in enumerate(files)
        if loc[i] >= 30 and os.path.exists(os.path.join(build_dir, os.path.join(prefix, f) if prefix else f))
    ]
    if len(candidates) < 4:
        return None
    sample = rng.sample(candidates, min(n_files, len(candidates)))

    baseline_cache: dict[tuple, float] = {}
    per_file = []
    total_secs = total_loc = 0.0
    total_baseline = 0.0
    for rel, l in sample:
        full = os.path.join(build_dir, rel)
        secs = time_lean(build_dir, rel, timeout)
        if secs is None:
            per_file.append({"file": rel, "loc": l, "secs": None})
            continue
        with open(full, encoding="utf-8", errors="replace") as f:
            head = f.read(20000)
        imports = tuple(re.findall(r"^import\s+\S+", head, re.M))
        if imports not in baseline_cache:
            stub = os.path.join(scratch, f"bench_stub_{key}.lean")
            with open(stub, "w") as f:
                f.write("\n".join(imports) + "\n")
            b = time_lean(build_dir, stub, timeout)
            baseline_cache[imports] = b if b is not None else 0.0
        base = baseline_cache[imports]
        elab = max(0.05, secs - base)
        per_file.append({"file": rel, "loc": l, "secs": round(secs, 2), "elab": round(elab, 2)})
        total_secs += elab
        total_loc += l
        total_baseline += base
    ok = [p for p in per_file if p.get("elab")]
    if not ok or total_loc == 0:
        return None
    rates = sorted(1000 * p["elab"] / p["loc"] for p in ok)
    return {
        "files": len(ok),
        "timeouts": len(per_file) - len(ok),
        "loc": int(total_loc),
        "secs": round(total_secs, 1),
        "baseline_secs": round(total_baseline / max(1, len(ok)), 2),
        "secs_per_kloc": round(1000 * total_secs / total_loc, 1),
        "secs_per_kloc_median": round(rates[len(rates) // 2], 1),
        "per_file": per_file,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-files", type=int, default=12)
    ap.add_argument("--timeout", type=int, default=150)
    ap.add_argument("--scratch", required=True)
    args = ap.parse_args()
    with open(args.config) as f:
        config = json.load(f)
    rng = random.Random(20260718)
    out = {}
    for key, cfg in config.items():
        print(f"[bench] {key} ...", flush=True)
        r = bench_repo(key, cfg, args.cache_dir, args.n_files, args.timeout,
                       args.scratch, rng)
        if r:
            out[key] = r
            print(f"[bench] {key}: {r['secs_per_kloc']} s/kLOC over {r['files']} files "
                  f"({r['timeouts']} timeouts)", flush=True)
        else:
            print(f"[bench] {key}: skipped", flush=True)
        with open(args.out, "w") as f:
            json.dump(out, f, indent=1)
    print(f"[bench] wrote {args.out}")


if __name__ == "__main__":
    main()
