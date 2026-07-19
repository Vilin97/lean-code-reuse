"""Lexical utilities for approximate Lean 4 source analysis.

Strips comments / string literals (preserving newlines so line numbers survive)
and tokenizes identifiers, including dotted names and common unicode ranges
used in Lean identifiers (Greek letters, subscripts, letterlike symbols).
"""

from __future__ import annotations

import re

# --- identifier syntax -------------------------------------------------------
# First char: letter, underscore, or unicode letter ranges Lean allows.
# We deliberately exclude operator/notation codepoints (∀ → ≤ ...) so they act
# as token separators.
_START = (
    r"A-Za-z_"
    r"Ͱ-Ͽ"          # Greek
    r"À-ÖØ-öø-ɏ"  # Latin-1 supplement / extended (minus × ÷)
    r"Ḁ-ỿ"          # Latin extended additional
    r"℀-⅏"          # letterlike (ℕ ℝ ℤ ...)
)
_CONT = _START + r"0-9'₀-ₜ"  # digits, prime, subscripts

_ATOM = rf"(?:[{_START}][{_CONT}]*|«[^»\n]*»)"
IDENT_RE = re.compile(rf"{_ATOM}(?:\.{_ATOM})*")

# Tokens that look like identifiers but are syntax, never declaration refs.
KEYWORDS = frozenset(
    """by fun do let have show from match with at in if then else calc where
    deriving this Type Prop Sort sorry admit stop open end exact_mod_cast
    obtain rcases rintro intro intros suffices ext use constructor exact apply
    refine rfl' nomatch nofun set_option variable variables universe
    """.split()
)

_EVENT = re.compile(r'--|/-|"|\'')


def strip_comments_and_strings(text: str) -> str:
    """Replace comments, string and char literals with spaces (newlines kept)."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        m = _EVENT.search(text, i)
        if not m:
            out.append(text[i:])
            break
        j = m.start()
        tok = m.group()
        if tok == "--":
            out.append(text[i:j])
            k = text.find("\n", j)
            if k == -1:
                k = n
            out.append(" " * (k - j))
            i = k
        elif tok == "/-":
            out.append(text[i:j])
            depth, k = 1, j + 2
            while depth and k < n:
                o = text.find("/-", k)
                c = text.find("-/", k)
                if c == -1:
                    k = n
                    break
                if o != -1 and o < c:
                    depth += 1
                    k = o + 2
                else:
                    depth -= 1
                    k = c + 2
            out.append(re.sub(r"[^\n]", " ", text[j:k]))
            i = k
        elif tok == '"':
            out.append(text[i:j])
            k = j + 1
            while k < n:
                c = text[k]
                if c == "\\":
                    k += 2
                    continue
                if c == '"':
                    k += 1
                    break
                k += 1
            out.append(re.sub(r"[^\n]", " ", text[j:k]))
            i = k
        else:  # single quote: char literal only when not part of an identifier
            prev = text[j - 1] if j > 0 else " "
            if re.match(rf"[{_CONT}]", prev):
                out.append(text[i : j + 1])
                i = j + 1
            else:
                m2 = re.match(r"'(?:\\.|[^'\\\n])'", text[j:])
                if m2:
                    out.append(text[i:j])
                    out.append(" " * m2.end())
                    i = j + m2.end()
                else:
                    out.append(text[i : j + 1])
                    i = j + 1
    return "".join(out)


# Bracket pairs used for depth-aware scanning of declaration bodies.
_OPEN = {"(": 1, "[": 1, "{": 1, "⟨": 1, "⦃": 1, "⟦": 1}
_CLOSE = {")": 1, "]": 1, "}": 1, "⟩": 1, "⦄": 1, "⟧": 1}


def find_toplevel(text: str, needles: tuple[str, ...], start: int = 0) -> tuple[int, str]:
    """First occurrence of any needle at bracket depth 0. Returns (pos, needle) or (-1, '')."""
    depth = 0
    i, n = start, len(text)
    while i < n:
        c = text[i]
        if c in _OPEN:
            depth += 1
        elif c in _CLOSE:
            depth = max(0, depth - 1)
        elif depth == 0:
            for nd in needles:
                if text.startswith(nd, i):
                    # ':=' must not be matched as ':' ; caller orders needles
                    return i, nd
        i += 1
    return -1, ""
