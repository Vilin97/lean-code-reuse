#!/bin/zsh
# Regenerate the full analysis + dashboard from scratch.
# Prereqs: python3+numpy, elan/lake, gh (for cloning), ~80GB disk, hours of build time.
set -e
WORK=${WORK:-/tmp/lean-reuse-work}
REPOS=$WORK/repos CACHE=$WORK/cache CACHE_ENV=$WORK/cache_env DUMPS=$WORK/dumps
mkdir -p $REPOS $DUMPS

# 1. Clone every registered repo (see lean_reuse/repos.py for the registry).
#    Shallow clones; lean4 needs sparse checkout of src/ only.
python3 - <<'PY'
from lean_reuse.repos import REPOS
for k, spec in REPOS.items():
    print(f"git clone --depth 1 {spec['url']} $REPOS/{spec['dir']}")
PY
echo "-- run the printed clones (branch 'gauss' for sphere-gauss), then:"

# 2. Build every repo (lake exe cache get && lake build in each). Proof dumps
#    that ship no lakefile need one first: guess the toolchain from the first
#    commit date (lakefile archaeology), or build the subproject that ships one
#    (Seed-Prover's imo2025, Erdős-90's src/submission). A repo that cannot be
#    built at all is DROPPED from the corpus — the dashboard is exact-tier only.
# 3. Textual tier over everything — now only a cross-check for §13, not a corpus
#    tier. Repos are never shipped on it.
python3 -m lean_reuse.run_all --repos-dir $REPOS --cache-dir $CACHE \
    --out $WORK/results_textual.json
# 4. Exact tier: extract env graphs from built repos (dyn variant avoids
#    notation clashes; enumerate built oleans under .lake/build/lib[/lean]):
#    python3 -m lean_reuse.extract_runner --repo-dir <repo> --imports <Root> \
#        --full-prefixes <Prefix> --out $DUMPS/<key>.tsv --scratch $DUMPS
#    Mathlib/Batteries/Aesop/core come free from any built downstream repo via
#    'import Mathlib' (see README "Exact-tier pipeline").
#    Collision-heavy corpora (files that redefine names across modules — ATLAS,
#    superhuman, Pedigree) cannot load as one environment. Two options:
#      a) greedy-drop: load all modules, drop whichever collides, retry — works
#         only when modules do NOT import each other (else the drop is undone
#         transitively). superhuman uses this (drops 1 of 31).
#      b) per-module: extract each module alone, then merge the dumps (envdump
#         accepts a comma-separated list; duplicate self-decls are folded). Use
#         for pedigree (all 40) and a deterministic ATLAS sample (180 of 2653).
# 5. Convert dumps (one repo, or a comma-separated list of per-module dumps):
#    python3 -m lean_reuse.envdump --dump $DUMPS/<key>.tsv --repos <key> \
#        --textual-cache-dir $CACHE --out-cache-dir $CACHE_ENV
# 6. Elaboration benchmark (writes bench.json; see bench_config in results/):
#    python3 -m lean_reuse.elab_bench --config bench_config.json \
#        --cache-dir $CACHE --out $WORK/bench.json --scratch $DUMPS
# 7. Metrics + validation + report:
python3 -m lean_reuse.run_all --repos-dir $REPOS --cache-dir $CACHE_ENV \
    --out $WORK/results_env.json --skip-build --bench $WORK/bench.json
python3 -m lean_reuse.validate_tiers --textual-cache-dir $CACHE \
    --env-cache-dir $CACHE_ENV --out $WORK/validation.json
python3 report/make_report.py --env $WORK/results_env.json \
    --textual $WORK/results_textual.json --validation $WORK/validation.json \
    --out docs/index.html
