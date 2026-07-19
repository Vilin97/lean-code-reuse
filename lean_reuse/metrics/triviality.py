"""M15 — Triviality and vacuity.

Community reviews of AI-generated PRs report declarations of type `True` and
lemmas like `1 + 1 = 2` padding out corpora. Detectable statically: statements
that normalize to `True` or contain only numerals/arithmetic (no named
concepts), statements referencing zero declarations, and one-liner
`trivial`/`rfl`/`decide` proofs.
"""

from __future__ import annotations

import numpy as np

NAME = "triviality"


def compute(data, prep, ctx) -> dict:
    thm = prep.is_theorem
    n = int(thm.sum())
    if n == 0:
        return {"pct_trivial_statements": None}
    m0 = prep.e_ctx == 0
    sig_out = np.bincount(prep.e_src[m0], minlength=prep.n)
    vac = (sig_out[thm] == 0)
    return {
        "pct_trivial_statements": round(float(prep.triv_stmt[thm].mean()), 4),
        "n_trivial_statements": int(prep.triv_stmt[thm].sum()),
        "pct_trivial_proofs": round(float(prep.triv_proof[thm].mean()), 4),
        "pct_statements_no_refs": round(float(vac.mean()), 4),
    }
