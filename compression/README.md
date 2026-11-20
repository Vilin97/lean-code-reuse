# Compression of Lean corpora (bits per byte)

How predictable is the source text of a Lean library? The study compresses eight corpora with
classical compressors and with small and medium language models, and reports **bits per byte
(bpb)** throughout: compressed bits / original UTF-8 bytes (8 / compression ratio). Lower bpb
means the text is more predictable to that compressor.

Results: [results.md](results.md) (tables) and [results.json](results.json) (all numbers).

## Findings

Headline (bpb, the same 16 random ~8 KB chunks per corpus, each compressed alone; whole-corpus
row: the entire corpus as one stream):

| Method | Mathlib | Tau Ceti | Lean Pool | Formal Frontier | OpenAI Math | CFSG | Stacks Core | Stacks Frontier |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| gzip -9 | 2.45 | 2.45 | 2.08 | 2.21 | 1.81 | 2.36 | 2.59 | 2.43 |
| PPMd o16 (best plain classical) | 2.06 | 2.09 | 1.75 | 1.85 | 1.51 | 1.99 | 2.22 | 2.07 |
| zstd -19 + own-corpus dictionary | 1.85 | 1.78 | 1.59 | 1.56 | 1.36 | 1.71 | 1.97 | 1.77 |
| SmolLM2-135M | 1.10 | 1.03 | 0.98 | 1.00 | 0.88 | 1.26 | 1.12 | 1.10 |
| Qwen3-0.6B | 0.69 | 0.66 | 0.63 | 0.65 | 0.68 | 0.82 | 0.75 | 0.72 |
| Qwen3-1.7B | 0.58 | 0.56 | 0.53 | 0.54 | 0.63 | 0.70 | 0.63 | 0.61 |
| Qwen3-4B | **0.49** | **0.48** | **0.47** | **0.47** | **0.58** | **0.62** | **0.55** | **0.53** |
| *best classical, whole corpus* | *1.10* | *1.00* | *0.87* | *0.97* | *0.78* | see results | *1.28* | *0.89* |

1. **LMs dominate at every scale tried.** On an isolated 8 KB chunk, even a 135M model needs
   about half the bits of the best classical compressor (1.35-1.75x fewer), and Qwen3-4B
   2.4-3.7x fewer. Qwen3-4B on 8 KB chunks also beats every classical compressor given the
   *whole* corpus as context (e.g. Mathlib 0.49 vs 1.10 for PPMd over all 95 MB).
2. **Within a model family, bpb falls steadily with size** (Qwen3 0.6B → 1.7B → 4B:
   0.69 → 0.58 → 0.49 on Mathlib; SmolLM2 135M → 360M: 1.10 → 0.89).
3. **Classical and LM rankings disagree on the generated-looking corpora.** OpenAI Math is
   the *most* compressible corpus classically (xz 0.68x Mathlib on chunks; 0.78 bpb whole) —
   it is full of templated, repeated text — but for Qwen3-4B it is *less* predictable than
   Mathlib (1.17x). CFSG is the least predictable corpus for every LM (1.26x Mathlib for
   Qwen3-4B) though about Mathlib-level classically: its proofs are dense term-mode
   arguments threading many idiosyncratically named local hypotheses (`hJ₀'L`, `hz₀'`). The
   larger the model, the larger the gap: repetition that classical coders exploit is not the
   same as being conventional Lean.
4. **Mathlib-style corpora sit together.** Tau Ceti, Lean Pool and Formal Frontier are within
   0.84-0.97x of Mathlib under every LM. No large memorisation advantage for Mathlib is
   visible at 8 KB context: Formal Frontier (2026, Mathlib style, not in pretraining) is
   *more* predictable than Mathlib for all models.
5. **Stacks: the human-reviewed tier is less predictable than the AI tier**, under every
   method (Qwen3-4B 0.55 vs 0.53; PPMd 2.22 vs 2.07; whole corpus 1.28 vs 0.89 — the last
   partly a size effect, 1.8 MB vs 1 GB). Stacks Core is also the least predictable corpus
   classically.
6. **A Lean prover fine-tune is worse, not better, at Lean source.** Kimina-Prover-Distill-1.7B
   (Qwen3-1.7B tuned for theorem proving) is 0.07-0.19 bpb worse than Qwen3-1.7B-Base on every
   corpus; Qwen2.5-Coder-1.5B is also behind Qwen3-1.7B-Base. Base pretraining scale matters
   more than code or Lean specialisation here.
7. Among classical coders on short chunks: PPMd > brotli (its built-in text dictionary helps)
   > zstd ≈ xz > gzip > bzip2; PPMd gains steadily with order up to 16. A dictionary trained
   on the corpus itself cuts zstd's bpb by 18-28%; one trained on Mathlib helps the
   Mathlib-style corpora (Tau Ceti, Formal Frontier: -23%) more than OpenAI Math (-8%) or
   CFSG (-13%).

## Corpora

The libraries and scopes of
[RemyDegenne/lean-quality-indicators](https://github.com/RemyDegenne/lean-quality-indicators)
(`libraries.toml`, plus its OpenAI Math and CFSG locks), at the same commits, plus the Stacks
Project in Lean. File counts and sizes agree exactly with that repository's
[compression run](https://github.com/RemyDegenne/lean-quality-indicators/blob/main/runs/compression-2026-11-03/results.md).

| Corpus | Repository | Scope | Commit |
|---|---|---|---|
| Mathlib | leanprover-community/mathlib4 | `Mathlib/` without `Tactic`, `Util`, `Lean`, `Testing`, `Deprecated` | `e3e75e8` |
| Tau Ceti | TauCetiProject/TauCeti | `TauCeti/` | `e8b7b60` |
| Lean Pool | Vilin97/lean-pool | `LeanPool/` | `01db1d7` |
| Formal Frontier | the 43 libraries of FormalFrontier | each repository's main `lean_lib` | pinned per repository |
| OpenAI Math | openai/math | `lean/OAI/` | `1581d4c` |
| CFSG (AxiomMath) | AxiomMath/CFSG | `CFSG/` | `5f8042b` |
| Stacks Core (reviewed) | AxiomMath/Stacks | `StacksCore/` (human-reviewed tier) | `f56a316` |
| Stacks Frontier (AI) | AxiomMath/Stacks | `StacksFrontier/` (AI-written tier) | `f56a316` |

Everywhere `*/Certificates/*` (machine-generated numerical certificates) is excluded, as upstream.
FLT (Anthropic), which the upstream repository also measures, is not in this study's list.
Stacks is split into its two tiers because they differ in review status; StacksFrontier is
99.8% of the repository's bytes.

## Method

1. **Sample** (`sample.py`). Each corpus is concatenated in path order (as upstream), cut into
   ~8 KB chunks at line boundaries, and 32 chunks are drawn uniformly at random (seed 0). A
   uniform draw over chunks is a uniform draw over bytes, so total bits / total bytes over the
   sample estimates the corpus's bpb at 8 KB context. The chunk order is shuffled, so a run
   limited to the first *k* chunks scores a random subset.
2. **Every method scores the same chunks, each on its own** (no context from neighbouring
   chunks), so the per-chunk numbers are paired across methods.
   - Classical (`classical.py`): gzip -9 (raw deflate), bzip2 -9, zstd -19, xz -9e (raw LZMA2),
     brotli -11, PPMd (var. H) orders 4/6/8/16. Container headers are stripped where the library
     allows it, so small chunks are not penalised for framing.
   - Classical with a prior: zstd -19 with a 112 KB dictionary trained on Mathlib chunks, and
     with one trained on the corpus's own chunks (the sampled chunks and their ±4 neighbours are
     left out of training). This is the classical counterpart of what pretraining gives an LM.
   - Language models (`lm_bpb.py`): the code length of a chunk is
     Σₜ −log₂ p(tokₜ | ⟨bos⟩, tok<ₜ), which arithmetic coding driven by the model achieves to
     within a couple of bits per chunk. Tokenizers are byte-level BPE; every chunk is checked to
     round-trip exactly. Models are base (pretrained) models except Kimina-Prover, a Lean
     theorem-proving fine-tune of Qwen3-1.7B. bf16 on CPU (bf16 vs fp32 differ by < 0.001 bpb).
3. **Whole corpus** (classical only): the concatenated corpus as one stream, with the window or
   model covering it (zstd `--long` window up to 2 GB, xz dictionary up to 192 MB, PPMd 2 GB),
   so repetition across files counts. This number falls as a corpus grows, so it is not
   comparable across corpora of very different size; the 8 KB-chunk numbers are.
4. **Report** (`report.py`): bpb per method and corpus on the chunks common to all methods,
   each method on all its chunks with a 95% bootstrap interval, medians, and ratios.

Compute: 4 CPU cores, no GPU, so LMs are capped at 4B parameters and larger models score fewer
chunks (see `results.md` for *k* per model). paq8px/cmix (the strongest context-mixing
compressors) are not included: building them from source was not available in this
environment.

## Caveats

- **Memorisation.** Older Mathlib is in the pretraining data of every model here; the 2026
  corpora are not. Some of Mathlib's LM bpb may be recall, although finding 4 suggests the
  effect is small at this context length. Formal Frontier and Stacks Core, recent
  Mathlib-style code, are the closest uncontaminated comparators.
- **Chunk counts differ by model**: SmolLM2-135M 32, SmolLM2-360M and Qwen3-0.6B 24, the
  1.5B-4B models 16 per corpus. Paired tables use the 16 chunks every method scored.
- **Low bpb is not quality.** A corpus of templated, generated or near-duplicate code compresses
  well under every method. LM bpb measures how conventional the text is relative to
  everything the model has read; classical bpb measures repetition inside the text.
- 32 chunks (fewer for the larger LMs) is a small sample of corpora with very skewed chunk
  distributions (a few generated-data chunks compress 10x better than the rest); compare the
  bootstrap intervals and medians before reading small differences.

## Reproduce

```bash
python3 -m compression.sample --corpora-dir <checkouts> --out-dir <work> --k 32
python3 -m compression.classical --work <work> chunks
python3 -m compression.classical --work <work> whole
python3 -m compression.lm_bpb --model Qwen/Qwen3-0.6B-Base --chunks <work>/chunks.jsonl \
    --out <work>/lm/Qwen_Qwen3-0.6B-Base.jsonl --limit 24
python3 -m compression.report --work <work>   # or with no --work: rebuild from compression/data
```
Checkouts: one directory per source (`mathlib`, `tauceti`, `lean-pool`,
`formal-frontier/<repo>`, `openai-math`, `cfsg`, `stacks`) at the commits above.
Requirements: `torch transformers zstandard brotli pyppmd`.
