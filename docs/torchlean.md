# TorchLean measurement

TorchLean is measured as a library corpus: `TorchLean/` only, with examples,
tests, and dependencies excluded from self declarations. FloatLib references
belong to the external `other` bucket. Authorship provenance is **Human + AI mix**,
based on the maintainers' [AI usage disclosure at the measured revision](https://github.com/lean-dojo/TorchLean/blob/bb95db148ab63e3beb3e9c43813ad782bdddad67/docs/CONTRIBUTING.md#ai-usage-disclosure).
They describe primarily manual development with AI assistance for proof
engineering, debugging, refactoring, and maintenance. This is a self-reported
classification, not a measured percentage of AI-written code. TorchLean is not
a quality calibration anchor. The initial `Unspecified` label was corrected
after locating this disclosure.

The initial measurement uses clean commit
`bb95db148ab63e3beb3e9c43813ad782bdddad67`, Lean 4.35.0, and the dependency
revisions in that checkout's `lake-manifest.json`. It reuses the user's built
`~/TorchLean` checkout. All 977 library modules were loaded; 969 contain
declarations retained by this project's contraction rules. The exact graph
contains 16,622 declarations and 1,077,226 edges, including external references.

Source metadata joins to 81.57% of retained declarations. Source-derived
metrics therefore retain the parser's limitations; extraction coverage is
complete. No elaboration-cost benchmark was run, so M13 is unavailable.
The revision, coverage, dependency pins, and dump checksum are recorded in
[`results/torchlean_measurement.json`](../results/torchlean_measurement.json).

## Reproduce from an existing build

Run these commands from the `lean-code-reuse` repository root. Use a clean
TorchLean checkout at the recorded revision for the same corpus. If it has not
been built, run `scripts/lake.sh exe cache get` and `scripts/lake.sh build`
inside that checkout first. Keep its selected build profile unchanged during
extraction.

```bash
set -euo pipefail
export TORCHLEAN_REPO="$HOME/TorchLean"
export REUSE_WORK=/tmp/lean-reuse-work

# Reuse the target's sources and pinned dependencies without copying or editing them.
python3 - <<'PY'
import os
from pathlib import Path
import subprocess

repo = Path(os.environ['TORCHLEAN_REPO']).resolve()
work = Path(os.environ['REUSE_WORK']).resolve()
prefix = Path(subprocess.check_output(
    ['lake', 'env', 'lean', '--print-prefix'], cwd=repo, text=True).strip())
targets = {
    'torchlean': repo,
    'mathlib4': repo / '.lake/packages/mathlib',
    'batteries': repo / '.lake/packages/batteries',
    'aesop': repo / '.lake/packages/aesop',
    'lean4/src': prefix / 'src/lean',
}
for name, target in targets.items():
    assert target.is_dir(), target
    link = work / 'sources' / name
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        assert link.resolve() == target.resolve(), link
    else:
        link.symlink_to(target, target_is_directory=True)

build = repo / '.lake/build/lib/lean'
sources = {'.'.join(p.relative_to(repo).with_suffix('').parts)
           for p in (repo / 'TorchLean').rglob('*.lean')}
built = {'.'.join(p.relative_to(build).with_suffix('').parts)
         for p in (build / 'TorchLean').rglob('*.olean')}
assert sources and sources == built, 'Build all library modules; check for stale artifacts'
(work / 'torchlean-modules.txt').write_text('\n'.join(sorted(sources)) + '\n')
PY

# Upstream caches are required for textual name resolution and the source whitelist.
python3 -m lean_reuse.run_all --repos-dir "$REUSE_WORK/sources" \
  --cache-dir "$REUSE_WORK/cache" --only core,batteries,aesop,mathlib4,torchlean \
  --force --nproc 4 --out "$REUSE_WORK/results_textual.json"

# There is no umbrella TorchLean module: import the complete module list.
python3 -m lean_reuse.extract_runner --repo-dir "$TORCHLEAN_REPO" \
  --imports "$(paste -sd, "$REUSE_WORK/torchlean-modules.txt")" \
  --full-prefixes TorchLean --dyn \
  --out "$REUSE_WORK/dumps/torchlean.tsv" --scratch "$REUSE_WORK/dumps"

python3 -m lean_reuse.envdump --dump "$REUSE_WORK/dumps/torchlean.tsv" \
  --repos torchlean --textual-cache-dir "$REUSE_WORK/cache" \
  --out-cache-dir "$REUSE_WORK/cache_env"
python3 -m lean_reuse.run_all --repos-dir "$REUSE_WORK/sources" \
  --cache-dir "$REUSE_WORK/cache_env" --only torchlean --skip-build \
  --out "$REUSE_WORK/torchlean_env.json"
python3 -m lean_reuse.validate_tiers --textual-cache-dir "$REUSE_WORK/cache" \
  --env-cache-dir "$REUSE_WORK/cache_env" --out "$REUSE_WORK/torchlean_validation.json"
```

Merge only the TorchLean row, preserving all other corpus measurements:

```bash
python3 - <<'PY'
import json, os
from pathlib import Path

work = Path(os.environ['REUSE_WORK'])
for filename, incoming in [
    ('results_env.json', 'torchlean_env.json'),
    ('results_textual.json', 'results_textual.json'),
    ('validation.json', 'torchlean_validation.json'),
]:
    path = Path('results') / filename
    data = json.loads(path.read_text())
    data['torchlean'] = json.loads((work / incoming).read_text())['torchlean']
    path.write_text(json.dumps(data, indent=1) + '\n')
PY
python3 report/make_report.py --env results/results_env.json \
  --textual results/results_textual.json --validation results/validation.json \
  --out docs/index.html
cp docs/index.html results/report.html
```

When changing the measured checkout, update `results/torchlean_measurement.json`
with its revision, dependency pins, extraction coverage, and new dump checksum.
Report generation writes local HTML only; publishing is a separate action.
