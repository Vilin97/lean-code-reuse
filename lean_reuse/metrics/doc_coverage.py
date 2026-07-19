"""M10 — Documentation coverage.

The Lean adaptation of classic comment-ratio / API-documentation metrics
(e.g. SIG maintainability's "unit documentation"): share of public
definitions and theorems carrying a docstring, plus overall comment density.
Mathlib enforces docstrings on new definitions via linter — a direct,
process-level quality signal that generated corpora rarely fake.
"""

from __future__ import annotations

import numpy as np

from . import KIND_IDX

NAME = "doc_coverage"

DEF_KINDS = np.array([KIND_IDX[k] for k in ("def", "abbrev", "structure", "class", "inductive")])


def compute(data, prep, ctx) -> dict:
    public = ~prep.anonymous & ~prep.private
    is_def = np.isin(prep.kind, DEF_KINDS) & public
    is_thm = prep.is_theorem & public
    fc = data.get("file_comment")
    fk = data.get("file_code")
    density = None
    if fc is not None and fk is not None:
        tot_c = int(sum(fc))
        tot_k = int(sum(fk))
        if tot_c + tot_k > 0:
            density = round(tot_c / (tot_c + tot_k), 4)
    return {
        "pct_defs_with_doc": round(float(prep.has_doc[is_def].mean()), 4) if is_def.any() else None,
        "pct_theorems_with_doc": round(float(prep.has_doc[is_thm].mean()), 4) if is_thm.any() else None,
        "pct_public_decls_with_doc": round(float(prep.has_doc[public & prep.is_target].mean()), 4)
        if (public & prep.is_target).any() else None,
        "comment_density": density,
    }
