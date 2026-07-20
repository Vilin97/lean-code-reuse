# lean-code-reuse

Website: https://vilin97.github.io/lean-code-reuse/

Macroscopic **quality metrics for Lean 4 formalization projects**. The study
began with the hypothesis that *internal reuse is the main statistical
signature of a high-quality library*; it ended somewhere more precise: raw
reuse volume is a coin flip, while **organization** (cross-directory reuse),
**process discipline** (docstrings, granular imports, sorry hygiene) and
**economy** (duplication, elaboration cost per line) discriminate low- from
high-quality corpora — regardless of whether a human or an AI wrote them.
Metrics are calibrated against declared quality anchors (maintainer-reviewed
projects vs unreviewed dumps), not against provenance.

## Measurement tiers

| tier | engine | needs a build? | what it sees |
|------|--------|----------------|--------------|
| **env** (exact) | Lean metaprogram over the elaborated `Environment` (`lean_reuse/extract/extract_template.lean`) | yes (`.olean`s) | true `getUsedConstants` of every declaration's type (statement) and value (proof/body): instances, notation-mediated refs, dot-notation — everything the kernel saw |
| **textual** (approximate) | regex/scoping parser (`lean_reuse/parser.py`, `resolver.py`) | no | direct name references with namespace/`open` resolution; misses dot-notation on locals (`μ.prod`), notation, and instance usage |

**Every corpus row on the dashboard is measured on the exact `env` tier.** Proof
dumps that ship no lakefile were built anyway — via lakefile archaeology (guess
the toolchain from the first commit date) or by building the subproject that
ships one (Seed-Prover's `imo2025`, Erdős-90's `src/submission`). Corpora whose
files redefine names across modules (ATLAS, superhuman, Pedigree) cannot load as
one environment; they are extracted one module at a time and the graphs merged
(`envdump.py` accepts a comma-separated dump list and folds duplicate
self-decls), with ATLAS measured on a deterministic 180-of-2653 module sample. A
repo that cannot be built at all is **dropped** from the corpus rather than
approximated. The textual tier survives only as the cross-check in §13 of the
report (it ranks hygiene/locality well, but cannot recover the amortization
exponent — which is why the corpus is exact-only).

### Exact-tier pipeline

1. `extract_runner.py` drops a generated script into a **built** target repo
   and runs `lake env lean` — the script walks `env.constants` and dumps an
   interned TSV graph (types vs values kept separate).
   Portability notes learned the hard way:
   - theorem proofs must be read via the `ConstantInfo` constructor fields —
     `value?` hides them on ≥4.32 toolchains (`allowOpaque`);
   - module names with dots in path segments need `«»` quoting;
   - AI repos can define notation that breaks `x[i]!` sugar in the script.
2. `envdump.py` converts a dump into per-repo caches, contracting
   compiler/attribute-generated constants (`match_*`, `proof_*`, equation
   lemmas, ctors, recursors, projections, `ext`/`injEq`/deriving instances)
   into their parent declaration. A *source whitelist* from the textual parse
   protects handwritten decls with generated-looking names (`False.elim`).
   Definitional plumbing folds its deps into the parent; attribute-generated
   API does not (that would create acausal cycles — the resulting graph is a
   clean DAG, `pct_in_cycles ≈ 0`).
3. One dump can yield several repo caches (a downstream repo's dump contains
   all of Mathlib + Batteries + Aesop + core).

## Metrics (one file each, `lean_reuse/metrics/`)

| # | module | question it answers |
|---|--------|---------------------|
| M1 | `reuse_degree` | How often is a declaration reused? (distinct-user in-degree: mean/median/tails, CCDF, % never reused) |
| M2 | `statement_vs_proof` | Is reuse load-bearing (statements/definitions) or only proof-quoting? |
| M3 | `cross_file` | Does reuse cross file/directory boundaries (shared vocabulary) or stay local (helper lemmas)? |
| M4 | `external_reuse` | Does the repo lean on Mathlib (refs per decl, vocabulary breadth) or reinvent it? |
| M5 | `concentration` | Gini / top-1% share of reuse: hub-and-spoke vs broad reuse |
| M6 | `dependency_depth` | Longest internal build-on chain (layered theory vs bag of facts) |
| M7 | `duplication` | Exact-duplicate bodies and statements (the failure mode reuse should punish) |
| M8 | `proof_economy` | Proof length, distinct lemmas per proof, `sorry` rate |
| M9 | `import_graph` | File-level fan-in, granular vs wholesale `import Mathlib` |
| M10 | `doc_coverage` | Docstring coverage on public defs, comment density (SE comment-ratio analog) |
| M11 | `complexity` | Branching tactic tokens per proof (McCabe cyclomatic adaptation) |
| M12 | `trust_base` | Declared axioms, `native_decide` reliance |
| M13 | `elab_cost` | Elaboration seconds per kLOC — heartbeats proxy, fed by `elab_bench.py` |

## Usage

```bash
# textual tier over all registered repos (clones in --repos-dir)
python3 -m lean_reuse.run_all --repos-dir <checkouts> --cache-dir cache \
    --out results_textual.json

# exact tier for one built repo
python3 -m lean_reuse.extract_runner --repo-dir <built repo> \
    --imports <RootModule> --full-prefixes <SelfPrefix> \
    --out dumps/repo.tsv --scratch dumps
python3 -m lean_reuse.envdump --dump dumps/repo.tsv --repos <key> \
    --textual-cache-dir cache --out-cache-dir cache_env
python3 -m lean_reuse.run_all --repos-dir . --cache-dir cache_env \
    --out results_env.json --skip-build
```

Repo registry lives in `lean_reuse/repos.py` (24 repos; core/Batteries/Aesop/
Formal-Conjectures/NNG4 are kept only as name-resolution upstreams — the
analysis corpus is 19 formalization projects: Mathlib, CSLib, Physlib,
SciLean, FLT, PFR, AddCombi, PNT+, Carleson, Tao's Analysis, Equational
Theories, LeanPool, TauCeti, StrongPNT, Meta ATLAS, Erdős-90, Clawristotle,
Seed-Prover, DeepMind superhuman).

Elaboration-cost benchmark:
```bash
python3 -m lean_reuse.elab_bench --config bench_config.json \
    --cache-dir cache --out bench.json --scratch /tmp
# then: python3 -m lean_reuse.run_all ... --bench bench.json
```
