"""M4 — Upstream (Mathlib / Batteries / core) reuse.

A downstream library that leans on Mathlib instead of reinventing it scores
higher: more upstream references per declaration and a broader vocabulary of
distinct upstream lemmas. Reinvention shows up as a low upstream/internal
ratio despite covering mathematical ground Mathlib already owns.
"""

from __future__ import annotations

import numpy as np

NAME = "external_reuse"


def compute(data, prep, ctx) -> dict:
    refs = data["repo_refs"]
    n_named = int((~prep.anonymous).sum())
    internal_cnt = int(prep.i_cnt.sum())
    per_dep = {}
    total_ext = 0
    mathlib_top = []
    for ridx in range(1, len(refs)):
        m = prep.e_repo == ridx
        cnt = int(prep.e_cnt[m].sum())
        vocab = int(len(np.unique(prep.e_dst[m])))
        per_dep[refs[ridx]] = {"refs": cnt, "distinct_decls_used": vocab}
        total_ext += cnt
        if refs[ridx] == "mathlib4" and cnt:
            id2name = (data.get("dep_names") or {}).get("mathlib4") or ctx.get(
                "dep_names", {}
            ).get("mathlib4")
            if id2name:
                dsts = prep.e_dst[m]
                cnts = prep.e_cnt[m]
                agg: dict[int, int] = {}
                for d, c in zip(dsts.tolist(), cnts.tolist()):
                    agg[d] = agg.get(d, 0) + c
                top = sorted(agg.items(), key=lambda kv: -kv[1])
                mathlib_top = []
                for dd, cc in top:
                    nm = id2name.get(dd, f"#{dd}")
                    if any(comp == "_" or comp.startswith("_") for comp in nm.split(".")):
                        continue  # parser artifacts / private plumbing
                    mathlib_top.append({"name": nm, "refs": cc})
                    if len(mathlib_top) >= 25:
                        break

    ml = per_dep.get("mathlib4", {"refs": 0, "distinct_decls_used": 0})
    return {
        "external_refs_total": total_ext,
        "external_refs_per_decl": round(total_ext / n_named, 3) if n_named else 0.0,
        "external_internal_ratio": round(total_ext / internal_cnt, 3) if internal_cnt else None,
        "per_dep": per_dep,
        "mathlib_refs_per_decl": round(ml["refs"] / n_named, 3) if n_named else 0.0,
        "mathlib_vocab": ml["distinct_decls_used"],
        "mathlib_vocab_per_1k_refs": round(1000 * ml["distinct_decls_used"] / ml["refs"], 1)
        if ml["refs"]
        else None,
        "top_mathlib": mathlib_top,
    }
