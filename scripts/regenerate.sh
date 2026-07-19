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

# 2. Build the buildable repos (lake exe cache get && lake build in each).
# 3. Textual tier over everything:
python3 -m lean_reuse.run_all --repos-dir $REPOS --cache-dir $CACHE \
    --out $WORK/results_textual.json
# 4. Exact tier: extract env graphs from built repos (dyn variant avoids
#    notation clashes; enumerate built oleans for repos with empty roots):
#    python3 -m lean_reuse.extract_runner --repo-dir <repo> --imports <Root> \
#        --full-prefixes <Prefix> --out $DUMPS/<key>.tsv --scratch $DUMPS
#    Mathlib/Batteries/Aesop/core come free from any built downstream repo via
#    'import Mathlib' (see README "Exact-tier pipeline").
# 5. Convert dumps:
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
