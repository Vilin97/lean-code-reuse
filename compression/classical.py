"""Classical compressors in bits per byte (8 * compressed bytes / original bytes).

Two scales:
  chunks  — each sampled ~8 KB chunk compressed alone (paired with the LM numbers);
  whole   — the whole concatenated corpus in one stream (window/model covering the corpus).

Framing overhead is stripped where the library allows it (raw deflate, raw LZMA2, zstd without
checksum/size/dict-id), so tiny chunks are not penalised for headers.

Two "prior knowledge" variants of zstd mirror what an LM brings to a chunk:
  zstd19+dict(mathlib)  112 KB dictionary trained on Mathlib chunks not in any sample
  zstd19+dict(self)     112 KB dictionary trained on the corpus's own non-sampled chunks
                        (sampled chunks and their +-4 neighbours are excluded from training)

    python3 -m compression.classical --work <work> chunks
    python3 -m compression.classical --work <work> whole [--only mathlib ...]
"""
from __future__ import annotations

import argparse
import bz2
import json
import lzma
import random
import sys
import time
import zlib
from pathlib import Path

import brotli
import pyppmd
import zstandard as zstd

from .corpora import ORDER
from .sample import chunk_bounds

FRAME = dict(write_checksum=False, write_content_size=False, write_dict_id=False)
XZ_FILTERS = [{"id": lzma.FILTER_LZMA2, "preset": 9 | lzma.PRESET_EXTREME}]
DICT_SIZE = 112 * 1024


def deflate(b: bytes) -> int:
    c = zlib.compressobj(9, zlib.DEFLATED, -15, 9)
    return len(c.compress(b) + c.flush())


def xz(b: bytes, dict_size: int | None = None) -> int:
    f = [dict(XZ_FILTERS[0])]
    if dict_size:
        f[0]["dict_size"] = dict_size
    return len(lzma.compress(b, format=lzma.FORMAT_RAW, filters=f))


def zstd_n(b: bytes, level: int = 19, dict_data=None, long_window: bool = False) -> int:
    if long_window:
        import math
        p = zstd.ZstdCompressionParameters.from_level(
            level, window_log=max(20, min(31, math.ceil(math.log2(max(len(b), 2))))),
            enable_ldm=True, **FRAME)
        return len(zstd.ZstdCompressor(compression_params=p).compress(b))
    return len(zstd.ZstdCompressor(level=level, dict_data=dict_data, **FRAME).compress(b))


def ppmd(b: bytes, order: int, mem: int = 256 << 20) -> int:
    enc = pyppmd.Ppmd7Encoder(order, mem)
    return len(enc.encode(b) + enc.flush(endmark=False))


CHUNK_METHODS = {
    "gzip-9": deflate,
    "bzip2-9": lambda b: len(bz2.compress(b, 9)),
    "xz-9e": xz,
    "zstd-19": zstd_n,
    "brotli-11": lambda b: len(brotli.compress(b, quality=11, lgwin=24)),
    "ppmd-o4": lambda b: ppmd(b, 4, 16 << 20),
    "ppmd-o6": lambda b: ppmd(b, 6, 16 << 20),
    "ppmd-o8": lambda b: ppmd(b, 8, 16 << 20),
    "ppmd-o16": lambda b: ppmd(b, 16, 16 << 20),
}


def train_dict(blob: bytes, exclude: set[int], n: int, seed: str) -> zstd.ZstdCompressionDict:
    bounds = chunk_bounds(blob)
    ok = [i for i in range(len(bounds)) if i not in exclude]
    rng = random.Random(seed)
    pick = rng.sample(ok, min(n, len(ok)))
    samples = [blob[bounds[i][0]:bounds[i][1]] for i in pick]
    return zstd.train_dictionary(DICT_SIZE, samples, k=1024, d=8, level=19)


def run_chunks(work: Path):
    chunks = [json.loads(l) for l in (work / "chunks.jsonl").read_text().splitlines()]
    blobs = {c: (work / "blobs" / f"{c}.bin") for c in ORDER}
    sampled: dict[str, set[int]] = {}
    for c in chunks:
        sampled.setdefault(c["corpus"], set()).update(range(c["id"] - 4, c["id"] + 5))
    dicts = {}
    t = time.time()
    mblob = blobs["mathlib"].read_bytes()
    dicts["mathlib"] = train_dict(mblob, sampled.get("mathlib", set()), 4000, "dict:mathlib")
    for cid in sampled:
        dicts["self:" + cid] = (dicts["mathlib"] if cid == "mathlib" else
                                train_dict(blobs[cid].read_bytes(), sampled[cid], 4000, "dict:" + cid))
    print(f"dictionaries trained in {time.time() - t:.0f}s", file=sys.stderr)
    out = []
    for c in chunks:
        b = c["text"].encode()
        r = dict(corpus=c["corpus"], id=c["id"], rank=c["rank"], bytes=len(b))
        for m, fn in CHUNK_METHODS.items():
            r[m] = 8 * fn(b) / len(b)
        r["zstd-19+dict(mathlib)"] = 8 * zstd_n(b, dict_data=dicts["mathlib"]) / len(b)
        r["zstd-19+dict(self)"] = 8 * zstd_n(b, dict_data=dicts["self:" + c["corpus"]]) / len(b)
        out.append(r)
    (work / "classical_chunks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in out))
    print("wrote", len(out), "chunk rows", file=sys.stderr)


WHOLE_METHODS = {
    "gzip-9": deflate,
    "bzip2-9": lambda b: len(bz2.compress(b, 9)),
    "zstd-19 --long": lambda b: zstd_n(b, 19, long_window=True),
    "xz-9e": lambda b: xz(b, dict_size=min(192 << 20, max(1 << 20, len(b)))),
    "ppmd-o8": lambda b: ppmd(b, 8, 2000 << 20),
    "ppmd-o16": lambda b: ppmd(b, 16, 2000 << 20),
}


def run_whole(work: Path, only: list[str] | None, methods: list[str] | None):
    path = work / "classical_whole.json"
    res = json.loads(path.read_text()) if path.exists() else {}
    for cid in only or ORDER:
        b = (work / "blobs" / f"{cid}.bin").read_bytes()
        res.setdefault(cid, {"bytes": len(b)})
        for m, fn in WHOLE_METHODS.items():
            if (methods and m not in methods) or m in res[cid]:
                continue
            t = time.time()
            n = fn(b)
            res[cid][m] = 8 * n / len(b)
            res[cid][m + " seconds"] = round(time.time() - t, 1)
            print(f"{cid:16s} {m:16s} {res[cid][m]:.4f} bpb  {time.time() - t:.0f}s",
                  file=sys.stderr, flush=True)
            path.write_text(json.dumps(res, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True, type=Path)
    ap.add_argument("what", choices=["chunks", "whole"])
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--methods", nargs="*")
    a = ap.parse_args()
    if a.what == "chunks":
        run_chunks(a.work)
    else:
        run_whole(a.work, a.only, a.methods)


if __name__ == "__main__":
    main()
