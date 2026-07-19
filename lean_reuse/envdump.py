"""Convert an environment-graph dump (exact tier) into metric caches.

One dump can yield caches for several repos (e.g. a lean-pool dump contains
LeanPool + all of Mathlib + Batteries + Aesop + core). Auxiliary constants
(`foo.match_1`, `foo._proof_2`, equation lemmas, constructors, recursors,
projections) are contracted into their parent source-level declaration so the
graph matches what a human would call "declarations".

Source-text stats (line counts, duplication hashes, imports) are joined from
the textual-tier cache by fully-qualified name.
"""

from __future__ import annotations

import os
import pickle
import re
import sys
from array import array

from .graphbuild import KIND_IDX

# module-prefix -> repo bucket used for dependency attribution
DEP_BUCKETS = [
    ("mathlib4", ("Mathlib",)),
    ("batteries", ("Batteries",)),
    ("aesop", ("Aesop",)),
    ("core", ("Init", "Std", "Lean", "Lake")),
]

ENV_SELF_PREFIXES = {
    "lean-pool": ("LeanPool",),
    "mathlib4": ("Mathlib",),
    "batteries": ("Batteries",),
    "aesop": ("Aesop",),
    "core": ("Init", "Std", "Lean"),
    "physlib": ("Physlib", "QuantumInfo"),
    "formal-conjectures": ("FormalConjectures", "FormalConjecturesForMathlib"),
    "cslib": ("Cslib",),
    "tauceti": ("TauCeti",),
    "analysis": ("Analysis",),
    "pfr": ("PFR",),
    "flt": ("FLT",),
    "atlas": ("Atlas",),
    "scilean": ("SciLean",),
    "equational_theories": ("equational_theories",),
    "nng4": ("Game",),
    "addcombi": ("AddCombi",),
    "pnt": ("PrimeNumberTheoremAnd",),
    "carleson": ("Carleson",),
    "strongpnt": ("StrongPNT",),
    "spherepacking": ("SpherePacking",),
    "sphere-gauss": ("SpherePacking",),
    "pedigree": ("MembershipProject", "Backup"),
    "rubik": ("RubiksCube",),
    "gblean": ("GB",),
}

# Auto-generated last name components. Only applied to names NOT found in the
# source-text whitelist, so handwritten decls with these names stay first-class.
AUX_LAST = re.compile(
    r"^(match_\d+(_\d+)*|proof_\d+|eq_\d+|eq_def|eq_unfold|below|ibelow|brecOn|"
    r"binductionOn|casesOn|recOn|rec|ndrec|ndrecOn|noConfusion|noConfusionType|"
    r"toCtorIdx|ofNat|sizeOf_spec|sizeOf_inst|injEq|inj|ctorIdx|ctorElim|"
    r"ctorElimType|elim|induct|induct_unfolding|mk|unary|congr_simp|congr(_\d+)?|"
    r"splitter|parenthesizer|formatter|else_eq|then_eq|default|go|ext|ext_iff|"
    r"repr|beq|decEq|hash|toJson|fromJson|eq|unfold|_.*)$"
)
# Plumbing aux constants elaborate from the parent's own body, so their deps
# can be folded into the parent without creating forward (acausal) edges.
# Other aux constants (attribute-generated API like `Foo.ext`) may be created
# later and reference later decls — contract them as targets, drop their deps.
PLUMBING_LAST = re.compile(
    r"^(match_\d+(_\d+)*|proof_\d+|_proof_\d+|eq_\d+|_eq_\d+|eq_def|eq_unfold|"
    r"splitter|go|unary|below|ibelow|brecOn|binductionOn|_aux.*|_sunfold|"
    r"_cstage\d*|_unfold|_simp_\d+)$"
)
SOURCE_KINDS = {"theorem", "def", "inductive", "axiom", "opaque", "instance"}

KIND_MAP = {
    "theorem": KIND_IDX["theorem"],
    "def": KIND_IDX["def"],
    "inductive": KIND_IDX["inductive"],
    "axiom": KIND_IDX["axiom"],
    "opaque": KIND_IDX["opaque"],
    "instance": KIND_IDX["instance"],
}


class Dump:
    __slots__ = ("modules", "names", "kind", "mod", "inst", "priv", "proj",
                 "tdeps", "vdeps", "by_name")

    def __init__(self) -> None:
        self.modules: list[str] = []
        self.names: list[str] = []
        self.kind: list[str] = []
        self.mod: list[str] = []
        self.inst: list[bool] = []
        self.priv: list[bool] = []
        self.proj: list[bool] = []
        self.tdeps: list = []
        self.vdeps: list = []
        self.by_name: dict[str, int] = {}


def parse_dump(path: str) -> Dump:
    d = Dump()
    intern = sys.intern
    kinds_cache: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for ln in f:
            if ln.startswith("C\t"):
                parts = ln.rstrip("\n").split("\t")
                _, _id, name, kind, mod, flags, td, vd = parts
                d.names.append(name)
                d.kind.append(kinds_cache.setdefault(kind, intern(kind)))
                d.mod.append(kinds_cache.setdefault(mod, intern(mod)))
                d.inst.append("i" in flags)
                d.priv.append("p" in flags)
                d.proj.append("j" in flags)
                d.tdeps.append(array("i", map(int, td.split())) if td.strip() else array("i"))
                d.vdeps.append(array("i", map(int, vd.split())) if vd.strip() else array("i"))
                if name not in d.by_name:
                    d.by_name[name] = len(d.names) - 1
            elif ln.startswith("M\t"):
                d.modules.append(ln[2:].strip())
    return d


def effective_kind(d: Dump, i: int) -> str:
    k = d.kind[i]
    if k == "def" and d.inst[i]:
        return "instance"
    return k


def is_source_level(d: Dump, i: int, source_names: set[str] | None = None) -> bool:
    """A constant counts as a declaration a human wrote.

    Kernel-generated kinds (ctor/rec/quot) and projections always contract.
    Otherwise a name seen in the textual parse of the source is trusted as
    source-level (protects handwritten `False.elim`-style names); names not
    in source fall back to the auto-generated-name pattern.
    """
    k = effective_kind(d, i)
    if k not in SOURCE_KINDS:
        return False
    if d.proj[i]:
        return False
    name = d.names[i]
    if "✝" in name:
        return False
    comps = name.split(".")
    if any(c.startswith("_") for c in comps):
        return False
    if source_names is not None and name in source_names:
        return True
    if AUX_LAST.match(comps[-1]):
        return False
    if source_names is not None:
        # unseen in source: generated names like `Foo.proof_2'`, `Foo.eq_3`
        # are already filtered above; remaining unseen names are kept only if
        # they look like ordinary declarations (instances often have no
        # source name at all, and macros generate legitimate decls).
        return True
    return True


def make_canon(d: Dump, source_names: set[str] | None = None):
    """Map constant id -> source-level ancestor id (or -1)."""
    memo: dict[int, int] = {}

    def is_source_level_(j: int) -> bool:
        return is_source_level(d, j, source_names)

    def canon(i: int) -> int:
        r = memo.get(i)
        if r is not None:
            return r
        memo[i] = -2  # cycle guard
        if is_source_level_(i):
            memo[i] = i
            return i
        name = d.names[i]
        comps = name.split(".")
        res = -1
        while len(comps) > 1:
            comps = comps[:-1]
            j = d.by_name.get(".".join(comps))
            if j is not None:
                if is_source_level_(j):
                    res = j
                    break
                jj = memo.get(j)
                if jj not in (None, -2) and jj >= 0:
                    res = jj
                    break
        memo[i] = res
        return res

    return canon


def build_env_cache(
    dump: Dump,
    key: str,
    spec_meta: dict,
    textual_cache: dict | None,
    source_names: set[str] | None = None,
) -> dict:
    self_prefixes = ENV_SELF_PREFIXES[key]

    def matches(mod: str, prefixes) -> bool:
        return any(mod == p or mod.startswith(p + ".") for p in prefixes)

    # bucket per module
    dep_keys = [k for k, _ in DEP_BUCKETS if k != key]
    repo_refs = [key] + dep_keys + ["other"]
    mod_bucket: dict[str, int] = {}
    for m in set(dump.mod):
        if matches(m, self_prefixes):
            mod_bucket[m] = 0
        else:
            b = len(repo_refs) - 1  # other
            for bi, (bk, prefixes) in enumerate(
                (k, p) for k, p in DEP_BUCKETS if k != key
            ):
                if matches(m, prefixes):
                    b = 1 + bi
                    break
            mod_bucket[m] = b

    canon = make_canon(dump, source_names)
    n_all = len(dump.names)

    # self source-level decls, ordered by (module, name)
    self_ids = [
        i for i in range(n_all)
        if mod_bucket[dump.mod[i]] == 0 and is_source_level(dump, i, source_names)
    ]
    self_ids.sort(key=lambda i: (dump.mod[i], dump.names[i]))
    local = {i: li for li, i in enumerate(self_ids)}
    n = len(self_ids)

    # files
    mods_sorted = sorted({dump.mod[i] for i in self_ids})
    file_of_mod = {m: fi for fi, m in enumerate(mods_sorted)}
    files = [m.replace(".", "/") + ".lean" for m in mods_sorted]

    # textual join
    tx_by_name: dict[str, int] = {}
    tx_file_stats: dict[str, tuple[int, list]] = {}
    tx = textual_cache
    if tx:
        for ti, nm in enumerate(tx["decls"]["name"]):
            if nm not in tx_by_name:
                tx_by_name[nm] = ti
        tfc = tx.get("file_comment")
        tfk = tx.get("file_code")
        for fi, f in enumerate(tx["files"]):
            tx_file_stats[f] = (
                tx["file_loc"][fi], tx["imports"][fi],
                tfc[fi] if tfc is not None else 0,
                tfk[fi] if tfk is not None else 0,
            )

    file_loc = array("i", (tx_file_stats.get(f, (0, [], 0, 0))[0] for f in files))
    imports = [tx_file_stats.get(f, (0, [], 0, 0))[1] for f in files]
    file_comment = array("q", (tx_file_stats.get(f, (0, [], 0, 0))[2] for f in files))
    file_code = array("q", (tx_file_stats.get(f, (0, [], 0, 0))[3] for f in files))

    # plumbing aux constants owned by each self decl (deps fold into parent).
    # Same-module only: equation lemmas / recursor equations can be *realized*
    # lazily in a later module, where their deps would create acausal edges.
    owned: dict[int, list[int]] = {}
    for i in range(n_all):
        if mod_bucket[dump.mod[i]] != 0 or i in local:
            continue
        if not PLUMBING_LAST.match(dump.names[i].split(".")[-1]):
            continue
        c = canon(i)
        if c not in local or dump.mod[i] != dump.mod[c]:
            continue
        # every component between the parent and the aux must itself be
        # plumbing — `AddCon.eq._simp_1` (generated lemma's simp aux) is not
        # definitional plumbing of `AddCon` and may reference later decls.
        parent = dump.names[c]
        name = dump.names[i]
        if not name.startswith(parent + "."):
            continue
        tail = name[len(parent) + 1 :].split(".")
        if all(PLUMBING_LAST.match(t) for t in tail):
            owned.setdefault(c, []).append(i)

    sorry_id = dump.by_name.get("sorryAx", -3)

    names_out: list[str] = []
    kind_a = array("b")
    file_a = array("i")
    line_a = array("i")
    anon_a = array("b", bytes(n))
    priv_a = array("b")
    doc_a = array("b")
    branch_a = array("i")
    tstmt_a = array("b")
    tproof_a = array("b")
    sorry_a = array("i")
    proof_lines = array("i")
    value_lines = array("i")
    sig_lines = array("i")
    sig_chars = array("i")
    proof_chars = array("i")
    sig_hash = array("q")
    body_hash = array("q")
    body_len = array("i")

    e_src = array("i")
    e_repo = array("b")
    e_dst = array("i")
    e_ctx = array("b")
    e_cnt = array("i")

    ext_used: dict[int, set[int]] = {}
    n_joined = 0

    for li, i in enumerate(self_ids):
        nm = dump.names[i]
        k = effective_kind(dump, i)
        names_out.append(nm)
        kind_a.append(KIND_MAP[k])
        file_a.append(file_of_mod[dump.mod[i]])
        priv_a.append(1 if dump.priv[i] else 0)

        ti = tx_by_name.get(nm)
        if ti is not None:
            n_joined += 1
            td = tx["decls"]
            doc_a.append(td["has_doc"][ti] if "has_doc" in td else 0)
            branch_a.append(td["branch"][ti] if "branch" in td else 0)
            tstmt_a.append(td["triv_stmt"][ti] if "triv_stmt" in td else 0)
            tproof_a.append(td["triv_proof"][ti] if "triv_proof" in td else 0)
            line_a.append(td["line"][ti])
            proof_lines.append(td["proof_lines"][ti])
            value_lines.append(td["value_lines"][ti])
            sig_lines.append(td["sig_lines"][ti] if "sig_lines" in td else 0)
            sig_chars.append(td["sig_chars"][ti])
            proof_chars.append(td["proof_chars"][ti])
            sig_hash.append(td["sig_hash"][ti])
            body_hash.append(td["body_hash"][ti])
            body_len.append(td["body_len"][ti])
        else:
            doc_a.append(0)
            branch_a.append(0)
            tstmt_a.append(0)
            tproof_a.append(0)
            line_a.append(0)
            sig_lines.append(0)
            proof_lines.append(0)
            value_lines.append(0)
            sig_chars.append(0)
            proof_chars.append(0)
            sig_hash.append(0)
            body_hash.append(0)
            body_len.append(0)

        is_thm = k in ("theorem", "axiom")
        vctx = 2 if is_thm else 1
        has_sorry = 0
        # (ctx, deps) streams: own type deps are signature; owned aux fold into value/proof
        streams = [(0, dump.tdeps[i]), (vctx, dump.vdeps[i])]
        for a in owned.get(i, ()):
            streams.append((vctx, dump.tdeps[a]))
            streams.append((vctx, dump.vdeps[a]))
        seen: set[tuple[int, int, int]] = set()
        for ctx0, deps in streams:
            for dep in deps:
                if dep == sorry_id:
                    has_sorry = 1
                    continue
                cd = canon(dep)
                if cd < 0:
                    continue
                b = mod_bucket[dump.mod[cd]]
                if b == 0:
                    dst = local.get(cd)
                    if dst is None or dst == li:
                        continue
                    tkey = (0, dst, ctx0)
                else:
                    tkey = (b, cd, ctx0)
                    ext_used.setdefault(b, set()).add(cd)
                if tkey in seen:
                    continue
                seen.add(tkey)
                e_src.append(li)
                e_repo.append(tkey[0])
                e_dst.append(tkey[1])
                e_ctx.append(ctx0)
                e_cnt.append(1)
        sorry_a.append(has_sorry)

    dep_names = {
        repo_refs[b]: {int(cd): dump.names[cd] for cd in ids}
        for b, ids in ext_used.items()
    }

    cache = {
        "key": key,
        "label": spec_meta["label"],
        "category": spec_meta["category"],
        "provenance": spec_meta["provenance"],
        "stars": spec_meta["stars"],
        "url": spec_meta["url"],
        "tier": "env",
        "files": files,
        "file_loc": file_loc,
        "file_comment": file_comment,
        "file_code": file_code,
        "imports": imports,
        "decls": {
            "name": names_out,
            "kind": kind_a,
            "file": file_a,
            "line": line_a,
            "anonymous": anon_a,
            "private": priv_a,
            "has_doc": doc_a,
            "branch": branch_a,
            "triv_stmt": tstmt_a,
            "triv_proof": tproof_a,
            "sorry": sorry_a,
            "proof_lines": proof_lines,
            "value_lines": value_lines,
            "sig_lines": sig_lines,
            "sig_chars": sig_chars,
            "proof_chars": proof_chars,
            "sig_hash": sig_hash,
            "body_hash": body_hash,
            "body_len": body_len,
        },
        "edges": {"src": e_src, "dst_repo": e_repo, "dst": e_dst, "ctx": e_ctx, "cnt": e_cnt},
        "repo_refs": repo_refs,
        "table": {nm: li for li, nm in enumerate(names_out)},
        "dep_names": dep_names,
        "stats": {
            "n_files": len(files),
            "n_parse_errors": 0,
            "loc": int(sum(file_loc)),
            "n_decls": n,
            "n_edges": len(e_src),
            "dotted_tokens": 1,
            "dotted_resolved": 1,
            "join_rate": round(n_joined / n, 4) if n else 0.0,
            "build_seconds": 0,
        },
    }
    return cache


def main() -> None:
    import argparse

    from .repos import REPOS

    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--repos", required=True, help="comma-separated repo keys to emit")
    ap.add_argument("--textual-cache-dir", required=True)
    ap.add_argument("--out-cache-dir", required=True)
    args = ap.parse_args()

    print(f"[envdump] parsing {args.dump} ...", flush=True)
    dump = parse_dump(args.dump)
    print(f"[envdump] {len(dump.names)} constants, {len(dump.modules)} modules", flush=True)
    os.makedirs(args.out_cache_dir, exist_ok=True)

    # whitelist of names actually written in source (self repos + upstream)
    source_names: set[str] = set()
    wl_keys = set(args.repos.split(",")) | {k for k, _ in DEP_BUCKETS}
    for wk in wl_keys:
        p = os.path.join(args.textual_cache_dir, wk + ".pkl")
        if os.path.exists(p):
            with open(p, "rb") as f:
                twc = pickle.load(f)
            anon = twc["decls"]["anonymous"]
            for ni, nm in enumerate(twc["decls"]["name"]):
                if not anon[ni]:
                    source_names.add(nm)
    print(f"[envdump] source whitelist: {len(source_names)} names", flush=True)

    for key in args.repos.split(","):
        tx_path = os.path.join(args.textual_cache_dir, key + ".pkl")
        tx = None
        if os.path.exists(tx_path):
            with open(tx_path, "rb") as f:
                tx = pickle.load(f)
        cache = build_env_cache(dump, key, REPOS[key], tx, source_names)
        out = os.path.join(args.out_cache_dir, key + ".pkl")
        with open(out, "wb") as f:
            pickle.dump(cache, f, protocol=4)
        s = cache["stats"]
        print(
            f"[envdump] {key}: files={s['n_files']} decls={s['n_decls']} "
            f"edges={s['n_edges']} join={s['join_rate']:.0%}",
            flush=True,
        )


if __name__ == "__main__":
    main()
