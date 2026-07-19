"""M12 — Trust base.

What must you believe beyond the kernel to accept this library? Counts
declared axioms, and (exact tier) declarations that directly invoke
`native_decide`-style trusted evaluation (`Lean.ofReduceBool` /
`Lean.trustCompiler`) or nonstandard axioms. The standard trio (propext,
Quot.sound, Classical.choice) plus sorryAx are tracked elsewhere.
"""

from __future__ import annotations

import numpy as np

from . import KIND_IDX

NAME = "trust_base"

NATIVE_NAMES = {"Lean.ofReduceBool", "Lean.ofReduceNat", "Lean.trustCompiler"}
STANDARD_AXIOMS = {"propext", "Quot.sound", "Classical.choice", "sorryAx", "Classical.choice.{u}"}


def compute(data, prep, ctx) -> dict:
    n_axioms = int((prep.kind == KIND_IDX["axiom"]).sum())
    axiom_names = [prep.names[i] for i in np.where(prep.kind == KIND_IDX["axiom"])[0][:12]]

    native_users = None
    dep_names = data.get("dep_names")
    if dep_names:
        native_ids = {
            int(i)
            for dep in dep_names.values()
            for i, nm in dep.items()
            if nm in NATIVE_NAMES
        }
        if native_ids:
            ext = prep.e_repo != 0
            hits = np.isin(prep.e_dst[ext], np.array(sorted(native_ids), dtype=np.int64))
            native_users = int(len(np.unique(prep.e_src[ext][hits])))
        else:
            native_users = 0
    return {
        "n_axioms_declared": n_axioms,
        "axioms_per_1k_decls": round(1000 * n_axioms / prep.n, 2) if prep.n else None,
        "axiom_names": axiom_names,
        "n_native_decide_users": native_users,
    }
