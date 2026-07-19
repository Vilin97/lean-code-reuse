"""Name resolution: turn declaration texts into a decl-level reference graph.

Resolution is approximate but mirrors Lean's scoping: try the enclosing
namespace chain (innermost first), then `open`ed namespaces, then the root.
A single trailing-component strip handles projection/dot chains like
`Foo.bar.mp` -> `Foo.bar`.
"""

from __future__ import annotations

from .lexer import IDENT_RE, KEYWORDS

CTX_SIG, CTX_VALUE, CTX_PROOF = 0, 1, 2
SORRY_TOKENS = frozenset({"sorry", "admit", "sorryAx", "sorry_proof"})
# branching tactic tokens — a textual proxy for cyclomatic complexity of proofs
BRANCH_TOKENS = frozenset({
    "cases", "cases'", "rcases", "obtain", "induction", "induction'",
    "split", "split_ifs", "by_cases", "match", "fin_cases", "interval_cases",
})


def resolve_decl(
    decl_id: int,
    file_idx: int,
    prefixes: tuple[str, ...],
    texts: tuple[str, str, str],  # sig, value, proof
    table: dict,
    self_private,  # array: private flag per self decl id
    self_file,     # array: file idx per self decl id
):
    """Returns (edges, sorries, branches, dotted, dotted_hit)."""
    edges: dict = {}
    sorries = 0
    branches = 0
    dotted = 0
    dotted_hit = 0

    def lookup(t: str):
        if t.startswith("_root_."):
            cands = ("",)
            t = t[len("_root_.") :]
        else:
            cands = prefixes
        for p in cands:
            h = table.get(p + t)
            if h is None:
                continue
            if h[0] == 0:
                j = h[1]
                if j == decl_id:
                    continue
                if self_private[j] and self_file[j] != file_idx:
                    continue
            return h
        return None

    for ctx, text in enumerate(texts):
        if not text:
            continue
        for m in IDENT_RE.finditer(text):
            t = m.group()
            if ctx != CTX_SIG and t in SORRY_TOKENS:
                sorries += 1
                continue
            if ctx == CTX_PROOF and t in BRANCH_TOKENS:
                branches += 1
                continue
            if t in KEYWORDS:
                continue
            is_dotted = "." in t
            if is_dotted:
                dotted += 1
            h = lookup(t)
            if h is None and is_dotted:
                h = lookup(t.rsplit(".", 1)[0])
            if h is None:
                continue
            if is_dotted:
                dotted_hit += 1
            key = (h[0], h[1], ctx)
            edges[key] = edges.get(key, 0) + 1
    return edges, sorries, branches, dotted, dotted_hit
