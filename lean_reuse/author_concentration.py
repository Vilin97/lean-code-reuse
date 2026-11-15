"""M17: concentration of surviving Lean code lines by Git author identity.

This is a separately pinned source/history measurement, not a Lean environment
metric or a claim about actual maintenance responsibility. No builds required.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import time

from . import lexer
from .repos import EXCLUDED_DIR_PARTS

METHOD = {
    "version": 1,
    "blame_options": ["--line-porcelain", "-w", "-M", "--ignore-revs-file="],
    "line_counter": "existing lexer: nonblank after stripping comments and literals",
    "identity": "snapshot mailmap, then normalized author email; hashed IDs in output",
    "lexer_sha256": hashlib.sha256(Path(lexer.__file__).read_bytes()).hexdigest(),
}
HEADER = re.compile(r"^[0-9a-f]{40,64} \d+ (\d+)(?: \d+)?$")


def _git(args, *, timeout=300):
    cp = subprocess.run(["git", *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        timeout=timeout, check=True)
    return cp.stdout


def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def measure_repo(repo_dir, roots, revision="HEAD", *, workers=4, cache_dir=None):
    """Measure all tracked Lean files under roots at one immutable revision.

    A missing scope, incomplete history or any failed file raises; callers must
    not present partial attribution as a complete project measurement.
    """
    started = time.monotonic()
    git_dir = _git(["-C", str(repo_dir), "rev-parse", "--absolute-git-dir"]).decode().strip()
    base = ["--git-dir=" + git_dir, "-c", "core.bare=true"]
    if _git(base + ["rev-parse", "--is-shallow-repository"]).strip() == b"true":
        raise ValueError("Shallow Git history: fetch complete history before attribution")
    rev = _git(base + ["rev-parse", "--verify", revision + "^{commit}"]).decode().strip()
    # Even for a working checkout, use this snapshot's mailmap, never uncommitted
    # identity mappings or a global mailmap.file. Bare mode avoids worktree input.
    tracked = _git(base + ["ls-tree", "-r", "--name-only", "-z", rev]).decode().split("\0")
    map_blob = rev + ":.mailmap" if ".mailmap" in tracked else ""
    base += ["-c", "mailmap.file=" + os.devnull, "-c", "mailmap.blob=" + map_blob,
             "-c", "blame.blankBoundary=false"]
    normalized_roots = []
    for root in roots:
        p = PurePosixPath(root)
        if p.is_absolute() or ".." in p.parts:
            raise ValueError("Source roots must be relative paths inside the repository")
        root = str(p).rstrip("/")
        if root != "." and not any(f == root or f.startswith(root + "/") for f in tracked):
            raise ValueError("Missing source root in pinned snapshot: " + root)
        normalized_roots.append(root)
    files = sorted({f for f in tracked if f.endswith(".lean")
                    and not any(p in EXCLUDED_DIR_PARTS for p in PurePosixPath(f).parts[:-1])
                    and any(r == "." or f == r or f.startswith(r + "/") for r in normalized_roots)})
    if not files:
        raise ValueError("No tracked Lean files found under the requested source roots")
    git_version = _git(["--version"]).decode().strip()
    cache_prefix = hashlib.sha256(json.dumps([rev, METHOD, git_version], sort_keys=True).encode()).hexdigest()

    def measure_file(path):
        cache_path = None
        if cache_dir:
            token = hashlib.sha256(path.encode()).hexdigest()
            cache_path = Path(cache_dir) / cache_prefix / (token + ".json")
            if cache_path.exists():
                result = json.loads(cache_path.read_text())
                if (result.get("path") == path and result.get("revision") == rev
                        and sum(a["sloc"] for a in result["authors"].values()) == result["sloc"]):
                    return result
                raise ValueError("Invalid attribution cache for " + path)
        source = _git(base + ["show", rev + ":" + path]).decode("utf-8", "replace")
        code_lines = {i for i, line in enumerate(lexer.strip_comments_and_strings(source).splitlines(), 1)
                      if line.strip()}
        authors = {}
        if code_lines:
            blame = _git(base + ["blame", *METHOD["blame_options"], rev, "--", path], timeout=900).decode("utf-8", "replace")
            seen = set()
            line_no = name = email = None
            for line in blame.splitlines():
                match = HEADER.match(line)
                if match:
                    line_no = int(match[1])
                    name = email = None
                elif line.startswith("author "):
                    name = line[7:]
                elif line.startswith("author-mail "):
                    email = line[12:].strip("<>").strip().casefold()
                elif line.startswith("\t") and line_no in code_lines:
                    if not name or email is None or line_no in seen:
                        raise ValueError("Missing or duplicate blame attribution for " + path)
                    seen.add(line_no)
                    identity = email if email else "name-only:" + name
                    aid = hashlib.sha256(identity.encode()).hexdigest()
                    author = authors.setdefault(aid, {"sloc": 0, "names": {},
                        "identity_basis": "email" if email else "name_only"})
                    author["sloc"] += 1
                    author["names"][name] = author["names"].get(name, 0) + 1
            if seen != code_lines:
                raise ValueError("Incomplete blame coverage for " + path)
        result = {"path": path, "revision": rev, "sloc": len(code_lines),
                  "physical_lines": len(source.splitlines()), "authors": authors}
        if cache_path:
            _write_json(cache_path, result)
        return result

    counts = Counter()
    names = defaultdict(Counter)
    name_only_ids = set()
    total_sloc = physical_lines = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for result in pool.map(measure_file, files):
            total_sloc += result["sloc"]
            physical_lines += result["physical_lines"]
            for aid, author in result["authors"].items():
                counts[aid] += author["sloc"]
                names[aid].update(author["names"])
                if author.get("identity_basis") == "name_only":
                    name_only_ids.add(aid)
    rows = []
    for aid, count in counts.items():
        # Most commonly attributed display name, with stable tie-breaking.
        name = min(names[aid], key=lambda n: (-names[aid][n], n.casefold(), n))
        rows.append({"id": aid, "name": name, "aliases": sorted(names[aid]),
                     "sloc": count, "share": count / total_sloc,
                     "identity_basis": "name_only" if aid in name_only_ids else "email"})
    rows.sort(key=lambda r: (-r["sloc"], r["name"].casefold(), r["id"]))
    top = rows[0] if rows else None
    return {
        "status": "ok", "revision": rev,
        "revision_date": _git(base + ["show", "-s", "--format=%cI", rev]).decode().strip(),
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "roots": normalized_roots, "excluded_directory_parts": sorted(EXCLUDED_DIR_PARTS),
        "scope": "all tracked Lean sources under registered library roots; separate from graph samples",
        "files": files, "files_measured": len(files), "total_sloc": total_sloc,
        "physical_lines": physical_lines, "n_authors": len(rows), "authors": rows,
        "top_author": top["name"] if top else None,
        "top_author_id": top["id"] if top else None,
        "top_author_sloc": top["sloc"] if top else 0,
        "top_author_share": top["share"] if top else None,
        "top_author_ties": [r["id"] for r in rows if top and r["sloc"] == top["sloc"]],
        "name_only_sloc": sum(counts[aid] for aid in name_only_ids),
        "identity_fallback": "missing email: group by exact author name, flagged separately",
        "history_complete": True, "method": METHOD, "git_version": git_version,
        "elapsed_seconds": round(time.monotonic() - started, 2),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", required=True, help="JSON: key -> repo_dir, roots, revision, url")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--repo-workers", type=int, default=2)
    ap.add_argument("--file-workers", type=int, default=4)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    manifest = json.loads(Path(args.manifest).read_text())
    selected = set(args.only.split(",")) if args.only else set(manifest)
    unknown = selected - manifest.keys()
    if unknown:
        ap.error("Unknown project keys: " + ", ".join(sorted(unknown)))
    # Pin every requested revision before starting potentially lengthy scans.
    pin_errors = {}
    for key, spec in manifest.items():
        if key in selected:
            try:
                spec["revision"] = _git(["-C", spec["repo_dir"], "rev-parse", "--verify",
                    spec.get("revision", "HEAD") + "^{commit}"]).decode().strip()
            except (OSError, subprocess.SubprocessError) as exc:
                pin_errors[key] = str(exc)
    out_path = Path(args.out)
    results = json.loads(out_path.read_text()) if out_path.exists() else {}
    failed = False

    def run(key):
        spec = manifest[key]
        print(f"[authors] {key}: starting {spec.get('revision', 'HEAD')[:12]}", flush=True)
        try:
            if key in pin_errors:
                raise ValueError(pin_errors[key])
            result = measure_repo(spec["repo_dir"], spec["roots"], spec["revision"],
                                  workers=args.file_workers, cache_dir=args.cache_dir)
            result["url"] = spec.get("url")
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            result = {"status": "error", "revision": spec.get("revision"), "roots": spec["roots"],
                      "url": spec.get("url"), "error": str(exc)}
        return key, result

    with ThreadPoolExecutor(max_workers=max(1, args.repo_workers)) as pool:
        pending = [pool.submit(run, k) for k in manifest if k in selected]
        for future in as_completed(pending):
            key, result = future.result()
            results[key] = result
            _write_json(out_path, results)
            if result["status"] == "ok":
                share = result["top_author_share"]
                share_text = f"{share:.2%}" if share is not None else "n/a"
                print(f"[authors] {key}: {result['total_sloc']:,} SLOC, "
                      f"top {result['top_author_sloc']:,} ({share_text}), "
                      f"{result['elapsed_seconds']}s", flush=True)
            else:
                failed = True
                print(f"[authors] {key}: ERROR {result['error']}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
