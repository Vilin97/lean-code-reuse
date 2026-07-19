"""M9 — File-level import graph.

Module organization: how many internal files does a typical file import, how
many files is a file imported by (fan-in), and whether downstream repos
import Mathlib wholesale (`import Mathlib`) instead of granular modules —
a hygiene signal that correlates with generated code.
"""

from __future__ import annotations

import numpy as np

NAME = "import_graph"

WHOLE_LIB_ROOTS = {"Mathlib", "Batteries", "Aesop", "Std", "Lean", "Init", "Cslib", "SciLean"}


def compute(data, prep, ctx) -> dict:
    files = data["files"]
    modules = {f[:-5].replace("/", "."): i for i, f in enumerate(files) if f.endswith(".lean")}
    n = len(files)
    fan_in = np.zeros(n, dtype=np.int64)
    internal_out = np.zeros(n, dtype=np.int64)
    whole_lib_files = 0
    ext_modules = set()
    for i, imps in enumerate(data["imports"]):
        whole = False
        for m in imps:
            j = modules.get(m)
            if j is not None:
                fan_in[j] += 1
                internal_out[i] += 1
            else:
                ext_modules.add(m)
                if m in WHOLE_LIB_ROOTS and m == "Mathlib":
                    whole = True
        if whole:
            whole_lib_files += 1
    locs = np.array([l for l in data.get("file_loc", [])]) if n else np.zeros(0)
    return {
        "median_file_loc": float(np.median(locs)) if len(locs) else None,
        "n_files": n,
        "mean_internal_imports_per_file": round(float(internal_out.mean()), 3) if n else 0.0,
        "median_fan_in": float(np.median(fan_in)) if n else 0.0,
        "pct_files_fan_in_ge2": round(float((fan_in >= 2).mean()), 4) if n else 0.0,
        "max_fan_in": int(fan_in.max()) if n else 0,
        "pct_files_importing_all_mathlib": round(whole_lib_files / n, 4) if n else 0.0,
        "n_distinct_external_modules": len(ext_modules),
    }
