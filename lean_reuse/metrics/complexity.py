"""M11 — Proof complexity (tactic branching).

A Lean adaptation of McCabe cyclomatic complexity: count branching tactic
tokens (`cases`, `rcases`, `obtain`, `induction`, `split`, `by_cases`,
`match`, ...) per proof. High branching with long proofs and few external
references marks monolithic case-bash proofs; libraries factor those into
lemmas. Textual token counts, joined into the exact tier by name.
"""

from __future__ import annotations

import numpy as np

NAME = "complexity"


def compute(data, prep, ctx) -> dict:
    thm = prep.is_theorem
    pl = prep.proof_lines[thm]
    br = prep.branch[thm]
    has = pl > 0
    if not has.any():
        return {"branch_per_proof": None, "branch_per_100_lines": None,
                "pct_proofs_branchy": None}
    total_br = int(br[has].sum())
    total_pl = int(pl[has].sum())
    return {
        "branch_per_proof": round(float(br[has].mean()), 3),
        "branch_per_100_lines": round(100 * total_br / total_pl, 2) if total_pl else None,
        "pct_proofs_branchy": round(float((br[has] >= 5).mean()), 4),
        "p90_branch": float(np.percentile(br[has], 90)),
    }
