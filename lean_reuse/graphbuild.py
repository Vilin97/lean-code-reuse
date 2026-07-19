"""Build and cache the per-repo declaration graph.

Pipeline per repo: collect .lean files -> parse (parallel) -> build combined
name table (self + dependency exports) -> resolve references (parallel via
fork) -> pack into a compact cache dict pickled to disk.
"""

from __future__ import annotations

import hashlib
import multiprocessing as mp
import os
import pickle
import time
from array import array

from .parser import parse_file, TARGET_KINDS, DECL_KINDS
from .repos import REPOS, EXCLUDED_DIR_PARTS
from .resolver import resolve_decl

KIND_IDX = {k: i for i, k in enumerate(DECL_KINDS)}


def collect_files(repo_dir: str, roots: list[str]) -> list[tuple[str, str]]:
    out = []
    for root in roots:
        base = os.path.join(repo_dir, root)
        if os.path.isfile(base) and base.endswith(".lean"):
            out.append((base, root))
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIR_PARTS]
            for fn in filenames:
                if fn.endswith(".lean"):
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, repo_dir)
                    out.append((full, rel))
    out.sort(key=lambda t: t[1])
    return out


def _parse_one(args):
    full, rel = args
    try:
        with open(full, encoding="utf-8", errors="replace") as f:
            text = f.read()
        return parse_file(full, rel, text)
    except Exception as e:  # keep going; report at the end
        from .parser import FileData
        fd = FileData(path=rel, module=rel)
        fd.loc = -1
        return fd


def _hash8(s: str) -> int:
    d = hashlib.blake2b(s.encode("utf-8", "replace"), digest_size=8).digest()
    return int.from_bytes(d, "little", signed=True)


# ---- resolution workers (fork-shared globals) -------------------------------
_G: dict = {}


def _resolve_chunk(rng):
    lo, hi = rng
    work = _G["work"]
    table = _G["table"]
    private = _G["private"]
    file_of = _G["file"]
    e_src = array("i")
    e_repo = array("b")
    e_dst = array("i")
    e_ctx = array("b")
    e_cnt = array("i")
    sorries = array("i")
    branches = array("i")
    dotted = 0
    dotted_hit = 0
    for i in range(lo, hi):
        decl_id, fidx, prefixes, sig, value, proof = work[i]
        edges, s, b, d, dh = resolve_decl(
            decl_id, fidx, prefixes, (sig, value, proof), table, private, file_of
        )
        sorries.append(s)
        branches.append(b)
        dotted += d
        dotted_hit += dh
        for (repo, dst, ctx), cnt in edges.items():
            e_src.append(decl_id)
            e_repo.append(repo)
            e_dst.append(dst)
            e_ctx.append(ctx)
            e_cnt.append(cnt)
    return lo, hi, e_src, e_repo, e_dst, e_ctx, e_cnt, sorries, branches, dotted, dotted_hit


def build_repo(key: str, repos_dir: str, dep_tables: dict[str, dict], nproc: int = 8) -> dict:
    spec = REPOS[key]
    repo_dir = os.path.join(repos_dir, spec["dir"])
    t0 = time.time()
    files = collect_files(repo_dir, spec["roots"])
    ctx = mp.get_context("fork")
    if len(files) > 200 and nproc > 1:
        with ctx.Pool(nproc) as pool:
            fds = pool.map(_parse_one, files, chunksize=32)
    else:
        fds = [_parse_one(f) for f in files]
    fds.sort(key=lambda fd: fd.path)
    n_parse_errors = sum(1 for fd in fds if fd.loc == -1)

    # ---- flatten decls -------------------------------------------------------
    file_names = [fd.path for fd in fds]
    file_loc = array("i", (max(fd.loc, 0) for fd in fds))
    file_comment = array("q", (fd.comment_chars for fd in fds))
    file_code = array("q", (fd.code_chars for fd in fds))
    imports = [fd.imports for fd in fds]

    names: list[str] = []
    kind = array("b")
    file_idx = array("i")
    line = array("i")
    anonymous = array("b")
    private = array("b")
    has_doc = array("b")
    proof_lines = array("i")
    value_lines = array("i")
    sig_lines = array("i")
    sig_chars = array("i")
    proof_chars = array("i")
    sig_hash = array("q")
    body_hash = array("q")
    body_len = array("i")
    work = []

    for fi, fd in enumerate(fds):
        for d in fd.decls:
            did = len(names)
            names.append(d.name)
            kind.append(KIND_IDX[d.kind])
            file_idx.append(fi)
            line.append(d.line)
            anonymous.append(1 if d.anonymous else 0)
            private.append(1 if d.private else 0)
            has_doc.append(1 if d.has_doc else 0)
            proof_lines.append(d.proof.count("\n") + (1 if d.proof.strip() else 0))
            value_lines.append(d.value.count("\n") + (1 if d.value.strip() else 0))
            sig_lines.append(d.sig.count("\n") + (1 if d.sig.strip() else 0))
            sig_chars.append(min(len(d.sig), 2**31 - 1))
            proof_chars.append(min(len(d.proof), 2**31 - 1))
            nsig = " ".join(d.sig.split())
            nbody = " ".join((d.value + " " + d.proof).split())
            sig_hash.append(_hash8(nsig))
            body_hash.append(_hash8(nbody))
            body_len.append(min(len(nbody), 2**31 - 1))
            work.append((did, fi, d.prefixes, d.sig, d.value, d.proof))

    # ---- name tables ---------------------------------------------------------
    self_table: dict[str, tuple[int, int]] = {}
    export_table: dict[str, int] = {}
    for did, nm in enumerate(names):
        if anonymous[did]:
            continue
        if nm not in self_table:
            self_table[nm] = (0, did)
        if not private[did] and nm not in export_table:
            export_table[nm] = did

    combined: dict[str, tuple[int, int]] = {}
    deps = spec["deps"]
    for pos in range(len(deps) - 1, -1, -1):
        dk = deps[pos]
        ridx = pos + 1
        for nm, did in dep_tables[dk].items():
            combined[nm] = (ridx, did)
    combined.update(self_table)

    # ---- resolve -------------------------------------------------------------
    _G["work"] = work
    _G["table"] = combined
    _G["private"] = private
    _G["file"] = file_idx

    n = len(work)
    chunk = max(1, n // (nproc * 8))
    ranges = [(lo, min(lo + chunk, n)) for lo in range(0, n, chunk)]
    e_src = array("i")
    e_repo = array("b")
    e_dst = array("i")
    e_ctx = array("b")
    e_cnt = array("i")
    sorry_cnt = array("i", bytes(4 * n))
    branch_cnt = array("i", bytes(4 * n))
    dotted = 0
    dotted_hit = 0
    if n > 2000 and nproc > 1:
        with ctx.Pool(nproc) as pool:
            for lo, hi, s, r, dd, c, cn, so, br, dt, dh in pool.imap_unordered(_resolve_chunk, ranges):
                e_src.extend(s)
                e_repo.extend(r)
                e_dst.extend(dd)
                e_ctx.extend(c)
                e_cnt.extend(cn)
                sorry_cnt[lo:hi] = so
                branch_cnt[lo:hi] = br
                dotted += dt
                dotted_hit += dh
    else:
        for rng in ranges:
            lo, hi, s, r, dd, c, cn, so, br, dt, dh = _resolve_chunk(rng)
            e_src.extend(s)
            e_repo.extend(r)
            e_dst.extend(dd)
            e_ctx.extend(c)
            e_cnt.extend(cn)
            sorry_cnt[lo:hi] = so
            branch_cnt[lo:hi] = br
            dotted += dt
            dotted_hit += dh
    _G.clear()

    cache = {
        "key": key,
        "label": spec["label"],
        "category": spec["category"],
        "provenance": spec["provenance"],
        "stars": spec["stars"],
        "url": spec["url"],
        "files": file_names,
        "file_loc": file_loc,
        "file_comment": file_comment,
        "file_code": file_code,
        "imports": imports,
        "decls": {
            "name": names,
            "kind": kind,
            "file": file_idx,
            "line": line,
            "anonymous": anonymous,
            "private": private,
            "has_doc": has_doc,
            "branch": branch_cnt,
            "sorry": sorry_cnt,
            "proof_lines": proof_lines,
            "value_lines": value_lines,
            "sig_lines": sig_lines,
            "sig_chars": sig_chars,
            "proof_chars": proof_chars,
            "sig_hash": sig_hash,
            "body_hash": body_hash,
            "body_len": body_len,
        },
        "edges": {
            "src": e_src, "dst_repo": e_repo, "dst": e_dst, "ctx": e_ctx, "cnt": e_cnt,
        },
        "repo_refs": [key] + list(deps),
        "table": export_table,
        "stats": {
            "n_files": len(file_names),
            "n_parse_errors": n_parse_errors,
            "loc": sum(file_loc),
            "n_decls": n,
            "n_edges": len(e_src),
            "dotted_tokens": dotted,
            "dotted_resolved": dotted_hit,
            "build_seconds": round(time.time() - t0, 1),
        },
    }
    return cache


def build_all(repos_dir: str, cache_dir: str, only: set[str] | None = None,
              force: bool = False, nproc: int = 8) -> None:
    from .repos import BUILD_ORDER

    os.makedirs(cache_dir, exist_ok=True)
    dep_tables: dict[str, dict] = {}

    def load_table(k: str) -> dict:
        if k not in dep_tables:
            with open(os.path.join(cache_dir, k + ".pkl"), "rb") as f:
                dep_tables[k] = pickle.load(f)["table"]
        return dep_tables[k]

    for k in BUILD_ORDER:
        path = os.path.join(cache_dir, k + ".pkl")
        if only is not None and k not in only:
            continue
        if os.path.exists(path) and not force:
            continue
        for dk in REPOS[k]["deps"]:
            load_table(dk)
        print(f"[build] {k} ...", flush=True)
        cache = build_repo(k, repos_dir, dep_tables, nproc=nproc)
        with open(path, "wb") as f:
            pickle.dump(cache, f, protocol=4)
        dep_tables[k] = cache["table"]
        s = cache["stats"]
        cov = s["dotted_resolved"] / max(1, s["dotted_tokens"])
        print(
            f"[build] {k}: files={s['n_files']} loc={s['loc']} decls={s['n_decls']} "
            f"edges={s['n_edges']} dotted-coverage={cov:.1%} "
            f"({s['build_seconds']}s, parse_errors={s['n_parse_errors']})",
            flush=True,
        )
