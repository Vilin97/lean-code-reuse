"""Bits per byte of text chunks under a causal language model (arithmetic-coding bound).

For a chunk of UTF-8 bytes x, the LM's code length is  sum_t -log2 p(tok_t | <bos>, tok_<t),
which an arithmetic coder driven by the model achieves to within ~2 bits per chunk.
bpb = code length / len(x). The tokenizer must be byte-level lossless (checked per chunk).
Long chunks are scored with a sliding window (window W, stride W/2, only new tokens scored).
Logits are materialised in slices so a 150k vocabulary does not need W x V floats at once.

    python3 -m compression.lm_bpb --model Qwen/Qwen3-0.6B-Base --chunks chunks.jsonl --out out.jsonl
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

LN2 = math.log(2)


def load(model_id: str, dtype=torch.bfloat16):
    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(model_id, dtype=dtype)
    model.eval()
    return tok, model


def start_token(tok) -> int:
    for t in (tok.bos_token_id, tok.eos_token_id, tok.pad_token_id):
        if t is not None:
            return t
    raise ValueError("tokenizer has no bos/eos token to condition the first token on")


@torch.inference_mode()
def code_length_bits(text: str, tok, model, window: int, slice_len: int = 1024) -> tuple[float, int]:
    ids = tok(text, add_special_tokens=False)["input_ids"]
    if tok.decode(ids, clean_up_tokenization_spaces=False) != text:
        raise ValueError("tokenizer is not lossless on this chunk")
    ids = [start_token(tok)] + ids
    n = len(ids)
    x = torch.tensor(ids)
    total_nats = 0.0
    scored = 1                      # position 0 (the start token) is context, not scored
    stride = window // 2
    begin = 0
    body = model.get_decoder() if hasattr(model, "get_decoder") else model.model
    head = model.get_output_embeddings()
    while scored < n:
        end = min(begin + window, n)
        inp = x[begin:end].unsqueeze(0)
        hidden = body(input_ids=inp).last_hidden_state[0]          # (L, d)
        # position i in the window predicts token begin+i+1; score tokens [scored, end)
        first = scored - begin - 1
        for s in range(first, end - begin - 1, slice_len):
            e = min(s + slice_len, end - begin - 1)
            logits = head(hidden[s:e]).float()
            logp = torch.log_softmax(logits, dim=-1)
            tgt = x[begin + s + 1: begin + e + 1]
            total_nats -= logp.gather(1, tgt.unsqueeze(1)).sum().item()
        scored = end
        if end == n:
            break
        begin = end - stride if end - stride > begin else end
    return total_nats / LN2, n - 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--chunks", required=True, help="jsonl with fields corpus, id, text")
    ap.add_argument("--out", required=True)
    ap.add_argument("--window", type=int, default=8192)
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0, help="only the first N chunks per corpus")
    args = ap.parse_args()
    if args.threads:
        torch.set_num_threads(args.threads)
    tok, model = load(args.model)
    out = Path(args.out)
    done = set()
    if out.exists():
        for line in out.read_text().splitlines():
            r = json.loads(line)
            done.add((r["corpus"], r["id"]))
    per_corpus: dict[str, int] = {}
    with out.open("a") as f:
        for line in open(args.chunks):
            c = json.loads(line)
            per_corpus[c["corpus"]] = per_corpus.get(c["corpus"], 0) + 1
            if args.limit and per_corpus[c["corpus"]] > args.limit:
                continue
            if (c["corpus"], c["id"]) in done:
                continue
            t = time.time()
            bits, ntok = code_length_bits(c["text"], tok, model, args.window)
            nbytes = len(c["text"].encode())
            r = dict(corpus=c["corpus"], id=c["id"], model=args.model, bytes=nbytes,
                     tokens=ntok, bits=bits, bpb=bits / nbytes, seconds=time.time() - t)
            f.write(json.dumps(r) + "\n")
            f.flush()
            print(f"{c['corpus']:16s} {c['id']:>6} {ntok:6d} tok {r['bpb']:.3f} bpb "
                  f"{ntok / r['seconds']:.0f} tok/s", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
