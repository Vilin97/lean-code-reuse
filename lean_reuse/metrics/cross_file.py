"""M3 — Cross-file reuse.

Reuse within a file is cheap (helper lemmas); reuse across files means the
declaration earned a place in the library's shared vocabulary. Measures the
share of internal reference pairs that cross file boundaries, how many
distinct files use a typical declaration, and cross-directory reuse.
"""

from __future__ import annotations

import numpy as np

NAME = "cross_file"


def _dir_of(path: str) -> str:
    parts = path.split("/")
    return "/".join(parts[: min(2, max(1, len(parts) - 1))])


def compute(data, prep, ctx) -> dict:
    if len(prep.p_src) == 0:
        return {
            "pct_edges_cross_file": 0.0, "pct_edges_cross_dir": 0.0,
            "pct_decls_used_outside_file": 0.0, "mean_user_files_per_used_decl": 0.0,
        }
    sf = prep.file[prep.p_src]
    df = prep.file[prep.p_dst]
    cross = sf != df

    dirs = np.array([_dir_of(p) for p in data["files"]])
    dir_ids = {d: i for i, d in enumerate(sorted(set(dirs)))}
    fdir = np.array([dir_ids[d] for d in dirs], dtype=np.int32)
    cross_dir = fdir[sf] != fdir[df]

    # distinct (target, user-file) pairs
    key = prep.p_dst.astype(np.int64) << 32 | sf.astype(np.int64)
    ukey = np.unique(key)
    tgt = (ukey >> 32).astype(np.int32)
    n_files_per = np.bincount(tgt, minlength=prep.n)
    # external file users only (exclude own file): recompute excluding same-file
    key2 = prep.p_dst[cross].astype(np.int64) << 32 | sf[cross].astype(np.int64)
    tgt2 = (np.unique(key2) >> 32).astype(np.int32)
    n_ext_files = np.bincount(tgt2, minlength=prep.n)

    t = prep.is_target
    used = n_files_per[t] > 0
    return {
        "pct_edges_cross_file": round(float(cross.mean()), 4),
        "pct_edges_cross_dir": round(float(cross_dir.mean()), 4),
        "pct_decls_used_outside_file": round(float((n_ext_files[t] >= 1).mean()), 4),
        "pct_decls_used_in_5plus_external_files": round(float((n_ext_files[t] >= 5).mean()), 4),
        "mean_user_files_per_used_decl": round(float(n_files_per[t][used].mean()) if used.any() else 0.0, 3),
        "n_dirs": len(dir_ids),
    }
