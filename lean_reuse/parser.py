"""Approximate parser for Lean 4 source files.

Extracts declarations (name, kind, namespace context, opens in scope) and
splits each declaration into signature / value / proof text. This is a
textual approximation — no elaboration — designed to be uniform across repos
so cross-repo comparisons are apples-to-apples.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .lexer import IDENT_RE, strip_comments_and_strings, _OPEN, _CLOSE

DECL_KINDS = (
    "theorem",
    "lemma",
    "proof_wanted",
    "def",
    "abbrev",
    "instance",
    "structure",
    "class",
    "inductive",
    "axiom",
    "opaque",
    "alias",
    "example",
    "macro_rules",
    "macro",
    "elab_rules",
    "elab",
    "notation3",
    "notation",
    "syntax",
)

THEOREM_LIKE = {"theorem", "lemma", "example", "proof_wanted"}
SIG_ONLY = {"structure", "class", "inductive", "axiom", "opaque"}
SYNTAX_KINDS = {"macro", "macro_rules", "elab", "elab_rules", "notation", "notation3", "syntax"}
# Kinds that count as reusable API surface (denominator for reuse metrics).
TARGET_KINDS = {
    "theorem", "lemma", "def", "abbrev", "structure", "class", "inductive",
    "axiom", "opaque", "alias",
}

_MODS = r"(?:(?:public|private|protected|noncomputable|unsafe|partial|nonrec|scoped|local|meta)\s+)*"
_KINDS_ALT = "|".join(DECL_KINDS).replace("class", r"class(?:\s+inductive|\s+abbrev)?", 1)
DECL_RE = re.compile(rf"^(?P<mods>{_MODS})(?P<kind>{_KINDS_ALT})(?![\w'])\s*(?P<rest>.*)$")

NAMESPACE_RE = re.compile(r"^namespace\s+([^\s]+)\s*$")
SECTION_RE = re.compile(r"^(?:noncomputable\s+|public\s+)*section(?:\s+([^\s]+))?\s*$")
END_RE = re.compile(r"^end(?:\s+([^\s]+))?\s*$")
OPEN_RE = re.compile(r"^open\s+(.*)$")
IMPORT_RE = re.compile(r"^(?:public\s+|meta\s+)?import\s+(?:all\s+)?([\w.«»\-]+)")
MUTUAL_RE = re.compile(r"^mutual\b")
SKIP_RE = re.compile(
    r"^(?:module\b|variable[s]?\b|universe\b|set_option\b|attribute\b|export\b|include\b|omit\b|"
    r"recall\b|#\w|run_cmd\b|initialize\b|builtin_initialize\b|deriving\s+instance\b|"
    r"recommended_spelling\b|register_\w+\b|declare_\w+\b|add_decl_doc\b|assert_not_exists\b|"
    r"library_note\b)"
)
ATTR_START_RE = re.compile(r"^@\[")


@dataclass
class Decl:
    name: str            # fully qualified (or synthetic for anonymous)
    kind: str
    file: str
    line: int
    end_line: int
    prefixes: tuple[str, ...]  # resolution prefixes, innermost first, '' last
    sig: str = ""
    value: str = ""
    proof: str = ""
    anonymous: bool = False
    private: bool = False
    has_doc: bool = False


@dataclass
class FileData:
    path: str
    module: str
    imports: list[str] = field(default_factory=list)
    decls: list[Decl] = field(default_factory=list)
    loc: int = 0  # non-blank stripped lines
    comment_chars: int = 0  # non-ws chars living in comments/docstrings
    code_chars: int = 0     # non-ws chars of stripped code


def _split_ns(name: str) -> list[str]:
    return [p for p in name.split(".") if p]


def _word_at(text: str, i: int, word: str) -> bool:
    if not text.startswith(word, i):
        return False
    before = text[i - 1] if i > 0 else " "
    after = text[i + len(word)] if i + len(word) < len(text) else " "
    return not re.match(r"[\w']", before) and not re.match(r"[\w']", after)


def split_decl_body(kind: str, text: str) -> tuple[str, str, str]:
    """Split decl text (after the name) into (sig, value, proof)."""
    if kind in SIG_ONLY:
        return text, "", ""
    if kind in SYNTAX_KINDS:
        return "", text, ""
    if kind == "alias":
        i = text.find(":=")
        return "", text[i + 2 :] if i >= 0 else text, ""
    depth = 0
    i, n = 0, len(text)
    line_start = True
    split = -1
    while i < n:
        c = text[i]
        if c in _OPEN:
            depth += 1
        elif c in _CLOSE:
            depth = max(0, depth - 1)
        elif depth == 0:
            if c == ":" and text.startswith(":=", i):
                split = i
                break
            if c == "|" and line_start and kind not in THEOREM_LIKE:
                split = i
                break
            if c == "w" and _word_at(text, i, "where"):
                split = i
                break
            if c == "b" and _word_at(text, i, "by") and kind in THEOREM_LIKE:
                # `theorem foo : P := by ...` is caught by ':=' first; this
                # handles rare `:= by` on a previous line / omitted `:=` forms.
                pass
        if c == "\n":
            line_start = True
        elif not c.isspace():
            line_start = False
        i += 1
    if split == -1:
        return text, "", ""
    head, tail = text[:split], text[split:]
    if kind in THEOREM_LIKE:
        return head, "", tail
    return head, tail, ""


def _parse_open_clause(clause: str, cur_ns: str) -> list[str]:
    """Parse the body of an `open` command into namespace names (absolute and
    relative-to-current candidates)."""
    clause = clause.strip()
    if clause.endswith(" in"):
        clause = clause[:-3]
    clause = re.sub(r"\brenaming\b.*$", "", clause)
    clause = re.sub(r"\bhiding\b.*$", "", clause)
    clause = re.sub(r"^scoped\s+", "", clause)
    # `open Foo (a b c)` — selective; keep just Foo
    clause = re.sub(r"\([^)]*\)", " ", clause)
    names = []
    for tok in clause.split():
        if IDENT_RE.fullmatch(tok):
            names.append(tok)
            if cur_ns:
                names.append(cur_ns + "." + tok)
    return names


class _Frame:
    __slots__ = ("kind", "parts", "opens")

    def __init__(self, kind: str, parts: list[str]):
        self.kind = kind
        self.parts = parts
        self.opens: list[str] = []


def parse_file(path: str, rel: str, text: str) -> FileData:
    stripped = strip_comments_and_strings(text)
    lines = stripped.split("\n")
    module = rel[:-5].replace("/", ".") if rel.endswith(".lean") else rel
    fd = FileData(path=rel, module=module)
    fd.loc = sum(1 for ln in lines if ln.strip())
    raw_nws = len(re.sub(r"\s", "", text))
    code_nws = len(re.sub(r"\s", "", stripped))
    fd.comment_chars = max(0, raw_nws - code_nws)
    fd.code_chars = code_nws
    # lines "covered" by a docstring: a `/-- ... -/` ending at line L covers
    # L+1..L+4 (attributes may sit between the docstring and the decl keyword)
    doc_cover: set[int] = set()
    for m in re.finditer(r"/--", text):
        end = text.find("-/", m.end())
        if end == -1:
            continue
        end_line = text.count("\n", 0, end) + 1
        doc_cover.update(range(end_line, end_line + 5))

    frames: list[_Frame] = [_Frame("file", [])]
    pending_opens: list[str] = []
    decls = fd.decls

    cur: Decl | None = None
    cur_body: list[str] | None = None
    cur_indent = 0
    anon_counter = 0

    def ns_parts() -> list[str]:
        parts: list[str] = []
        for f in frames:
            parts.extend(f.parts)
        return parts

    def all_opens() -> list[str]:
        o: list[str] = []
        for f in reversed(frames):
            o.extend(f.opens)
        return o

    def close_current(end_line: int) -> None:
        nonlocal cur, cur_body
        if cur is None:
            return
        body = "\n".join(cur_body)
        cur.sig, cur.value, cur.proof = split_decl_body(cur.kind, body)
        cur.end_line = end_line
        decls.append(cur)
        cur, cur_body = None, None

    def make_prefixes(extra_ns: list[str]) -> tuple[str, ...]:
        parts = ns_parts() + extra_ns
        prefixes: list[str] = []
        for k in range(len(parts), 0, -1):
            prefixes.append(".".join(parts[:k]) + ".")
        for o in all_opens() + pending_opens:
            p = o + "."
            if p not in prefixes:
                prefixes.append(p)
        prefixes.append("")
        return tuple(prefixes)

    i = 0
    n_lines = len(lines)
    while i < n_lines:
        raw = lines[i]
        s = raw.strip()
        lineno = i + 1
        if not s:
            if cur_body is not None:
                cur_body.append(raw)
            i += 1
            continue
        indent = len(raw) - len(raw.lstrip())
        structural_ok = cur is None or indent <= cur_indent

        if structural_ok:
            # ---- attribute block (may span lines, may precede a decl) ----
            if ATTR_START_RE.match(s):
                close_current(lineno - 1)
                j, bal, pos = i, 0, -1
                seen_open = False
                while j < n_lines and pos == -1:
                    for k, ch in enumerate(lines[j]):
                        if ch == "[":
                            bal += 1
                            seen_open = True
                        elif ch == "]":
                            bal -= 1
                            if seen_open and bal == 0:
                                pos = k + 1
                                break
                    if pos == -1:
                        j += 1
                if pos == -1:
                    i = n_lines
                    continue
                remainder = lines[j][pos:].strip()
                if remainder:
                    lines[j] = " " * indent + remainder
                    i = j
                else:
                    i = j + 1
                continue

            m = IMPORT_RE.match(s)
            if m:
                close_current(lineno - 1)
                fd.imports.append(m.group(1))
                i += 1
                continue
            m = NAMESPACE_RE.match(s)
            if m:
                close_current(lineno - 1)
                frames.append(_Frame("namespace", _split_ns(m.group(1))))
                i += 1
                continue
            m = SECTION_RE.match(s)
            if m and s.split()[0] in ("section", "noncomputable", "public"):
                close_current(lineno - 1)
                frames.append(_Frame("section", []))
                i += 1
                continue
            m = END_RE.match(s)
            if m:
                close_current(lineno - 1)
                if len(frames) > 1:
                    frames.pop()
                i += 1
                continue
            if MUTUAL_RE.match(s):
                close_current(lineno - 1)
                frames.append(_Frame("mutual", []))
                i += 1
                continue
            m = OPEN_RE.match(s)
            if m:
                close_current(lineno - 1)
                clause = m.group(1)
                cur_ns = ".".join(ns_parts())
                names = _parse_open_clause(clause, cur_ns)
                if re.search(r"\bin\s*$", clause):
                    pending_opens.extend(names)
                elif re.search(r"\bin\b", clause):
                    # `open X in <decl on same line>`
                    pending_opens.extend(names)
                    rest = re.split(r"\bin\b", clause, maxsplit=1)[1].strip()
                    if rest:
                        lines[i] = " " * indent + rest
                        continue
                else:
                    frames[-1].opens.extend(names)
                i += 1
                continue
            if SKIP_RE.match(s):
                close_current(lineno - 1)
                if re.match(r"^set_option\b.*\bin\s*$", s) or re.match(r"^include\b.*\bin\s*$", s):
                    pass  # applies to next decl; nothing to track
                i += 1
                continue

            dm = DECL_RE.match(s)
            if dm:
                close_current(lineno - 1)
                kind = dm.group("kind").split()[0]
                mods = dm.group("mods") or ""
                rest = dm.group("rest")
                name = None
                if kind == "alias":
                    am = re.match(rf"⟨\s*({IDENT_RE.pattern})\s*,\s*({IDENT_RE.pattern})\s*⟩", rest)
                    if am:
                        # `alias ⟨mp, mpr⟩ := thm`; either side may be `_`
                        name = am.group(1) if am.group(1) != "_" else am.group(2)
                    else:
                        am = re.match(rf"({IDENT_RE.pattern})", rest)
                        name = am.group(1) if am else None
                    if name == "_":
                        name = None
                elif kind in SYNTAX_KINDS:
                    nm = re.search(rf"\(\s*name\s*:=\s*({IDENT_RE.pattern})\s*\)", rest)
                    name = nm.group(1) if nm else None
                elif kind not in ("example",):
                    r2 = rest
                    r2 = re.sub(r"^\(\s*priority\s*:=[^)]*\)\s*", "", r2)
                    nm = re.match(rf"({IDENT_RE.pattern})", r2)
                    if nm and kind == "instance" and r2[nm.end() : nm.end() + 1] not in (
                        " ", ":", "\t", "", ".", "(", "[", "{",
                    ):
                        nm = None
                    name = nm.group(1) if nm else None
                    if name is not None:
                        r3 = r2[len(name):]
                        um = re.match(r"\.\{[^}]*\}", r3)
                        rest = r2[len(name) + (um.end() if um else 0):]
                    else:
                        rest = r2

                if name == "_":
                    name = None
                extra_ns: list[str] = []
                anonymous = False
                if name is None:
                    anon_counter += 1
                    name = f"{'.'.join(ns_parts() + [''])}__{kind}✝{anon_counter}@{module}"
                    anonymous = True
                    fqn = name
                else:
                    if name.startswith("_root_."):
                        fqn = name[len("_root_.") :]
                    else:
                        fqn = ".".join(ns_parts() + [name]) if ns_parts() else name
                    comps = _split_ns(fqn)
                    if len(comps) > 1:
                        extra_ns = comps[:-1]
                # prefixes: namespace chain (incl. decl's own ns) > opens > root
                saved = pending_opens[:]
                prefixes = make_prefixes(extra_ns)
                pending_opens.clear()
                del saved

                cur = Decl(
                    name=fqn,
                    kind=kind,
                    file=rel,
                    line=lineno,
                    end_line=lineno,
                    prefixes=prefixes,
                    anonymous=anonymous or kind == "example",
                    private="private" in mods,
                    has_doc=lineno in doc_cover,
                )
                cur_indent = indent
                cur_body = [rest]
                i += 1
                continue

        # continuation line
        if cur_body is not None:
            cur_body.append(raw)
        i += 1

    close_current(n_lines)
    return fd
