# Compression of Lean corpora (bits per byte)

How predictable is the source text of a Lean library? The study compresses eight corpora with
classical compressors and with small and medium language models, and reports **bits per byte
(bpb)** throughout: compressed bits / original UTF-8 bytes (8 / compression ratio). Lower bpb
means the text is more predictable to that compressor.

Results: [results.md](results.md) (tables) and [results.json](results.json) (all numbers).

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

- **Memorisation.** Mathlib (and, to a lesser degree, older Lean code generally) is in the
  pretraining data of every model here; the AI-written corpora (2026) and Stacks are not. LM
  bpb on Mathlib is therefore partly recall. Formal Frontier and Stacks Core, recent
  Mathlib-style code, are the closest uncontaminated comparators.
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
python3 -m compression.report --work <work>
```
Checkouts: one directory per source (`mathlib`, `tauceti`, `lean-pool`,
`formal-frontier/<repo>`, `openai-math`, `cfsg`, `stacks`) at the commits above.
Requirements: `torch transformers zstandard brotli pyppmd`.
