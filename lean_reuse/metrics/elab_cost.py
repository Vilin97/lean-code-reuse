"""M13 — Elaboration cost per LOC (heartbeats proxy).

Hypothesis: low-quality corpora make the elaborator work harder per line —
brute-force tactic calls (`decide`, `nlinarith`, `polyrith`, giant `simp`
sets) instead of the right lemma. Measured by re-elaborating a random sample
of already-built files with `lake env lean` and timing them; the per-file
import-loading baseline (a stub with the same imports) is subtracted, so the
number approximates pure elaboration seconds per kLOC — a wall-clock stand-in
for heartbeats/LOC. Data produced by `lean_reuse/elab_bench.py`.
"""

from __future__ import annotations

NAME = "elab_cost"


def compute(data, prep, ctx) -> dict:
    bench = (ctx.get("bench") or {}).get(data["key"])
    if not bench:
        return {"secs_per_kloc": None}
    return {
        "secs_per_kloc": bench.get("secs_per_kloc"),
        "secs_per_kloc_median": bench.get("secs_per_kloc_median"),
        "files_sampled": bench.get("files"),
        "loc_sampled": bench.get("loc"),
        "import_baseline_secs": bench.get("baseline_secs"),
    }
