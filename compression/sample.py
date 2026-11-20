"""Concatenate each corpus in path order, cut it into ~8 KB line-aligned chunks, and draw a
fixed uniform random sample of chunks (seed 0). Every compressor (classical and LM) is scored
on exactly these chunks, each compressed on its own, so the per-chunk numbers are paired.

Uniform over chunks = uniform over bytes, so total bits / total bytes over the sample is an
unbiased estimate of the corpus's bits per byte at 8 KB context.

    python3 -m compression.sample --corpora-dir <checkouts> --out-dir <work>
writes <work>/blobs/<corpus>.bin (whole concatenated corpus), <work>/chunks.jsonl,
<work>/corpus_stats.json
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from .corpora import CORPORA, files_of

CHUNK = 8192


def chunk_bounds(blob: bytes, size: int = CHUNK) -> list[tuple[int, int]]:
    """Grid cuts at multiples of `size`, each moved forward to the next line start."""
    cuts = [0]
    for k in range(size, len(blob), size):
        j = blob.find(b"\n", k)
        if j < 0:
            break
        j += 1
        if j > cuts[-1]:
            cuts.append(j)
    if cuts[-1] < len(blob):
        cuts.append(len(blob))
    bounds = list(zip(cuts, cuts[1:]))
    if bounds and bounds[-1][1] - bounds[-1][0] < size // 2:
        bounds.pop()          # drop a short tail chunk
    return bounds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpora-dir", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--k", type=int, default=32)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    (args.out_dir / "blobs").mkdir(parents=True, exist_ok=True)
    stats_path = args.out_dir / "corpus_stats.json"
    stats = json.loads(stats_path.read_text()) if stats_path.exists() else {}
    chunks_path = args.out_dir / "chunks.jsonl"
    old = [json.loads(l) for l in chunks_path.read_text().splitlines()] if chunks_path.exists() else []
    ids = args.only or list(CORPORA)
    keep = [c for c in old if c["corpus"] not in ids]
    new = []
    for cid in ids:
        files = files_of(cid, args.corpora_dir)
        parts, starts, pos = [], [], 0
        for disp, p in files:
            b = p.read_bytes()
            if b and not b.endswith(b"\n"):
                b += b"\n"
            parts.append(b)
            starts.append((pos, disp))
            pos += len(b)
        blob = b"".join(parts)
        (args.out_dir / "blobs" / f"{cid}.bin").write_bytes(blob)
        bounds = chunk_bounds(blob)
        rng = random.Random(f"{args.seed}:{cid}")
        pick = sorted(rng.sample(range(len(bounds)), min(args.k, len(bounds))))
        order = list(pick)
        rng.shuffle(order)                   # LM runs with --limit take a random subset
        import bisect
        offs = [s for s, _ in starts]
        for rank, i in enumerate(order):
            a, b = bounds[i]
            fidx = bisect.bisect_right(offs, a) - 1
            new.append(dict(corpus=cid, id=i, rank=rank, start=a, end=b,
                            file=starts[fidx][1], text=blob[a:b].decode("utf-8")))
        stats[cid] = dict(name=CORPORA[cid]["name"], files=len(files), bytes=len(blob),
                          chunks=len(bounds))
        print(cid, len(files), "files", f"{len(blob) / 1e6:.1f} MB", len(bounds), "chunks")
    new.sort(key=lambda c: (list(CORPORA).index(c["corpus"]), c["rank"]))
    with chunks_path.open("w") as f:
        for c in sorted(keep + new, key=lambda c: (list(CORPORA).index(c["corpus"]), c["rank"])):
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    stats_path.write_text(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
