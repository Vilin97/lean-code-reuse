# FloatLib measurement

FloatLib is included in the exact graph, textual cross-checks, source metrics,
PCA, composite and architecture comparisons, and Git author concentration (M17).
The measured revision is `acba2057e452f32f4ed4f06bb0adbeda5342ba92`, using
Lean 4.35.0 and its pinned dependency manifest. Existing projects' saved
measurements are preserved; comparisons are regenerated with 27 projects.

The scope contains the `FloatLib/Floats`, `FloatLib/Numerics` and
`FloatLib/Kernels` trees, their three umbrella files, and `FloatLib.lean`.
Worked examples under `FloatLib/Examples`, their umbrella file, tests,
benchmarks, the website and dependencies are excluded. The registry lists these
roots explicitly so source metrics and Git attribution use the same scope.

The provenance label is **Human + AI mix**, based on the pinned
[README](https://github.com/lean-dojo/FloatLib/blob/acba2057e452f32f4ed4f06bb0adbeda5342ba92/README.md#L135-L139)
and [formalization manifest](https://github.com/lean-dojo/FloatLib/blob/acba2057e452f32f4ed4f06bb0adbeda5342ba92/formalization.yaml#L106-L114).
These disclose manual foundations and AI help completing proofs and optimizing
arithmetic backends. This is a self-reported provenance label, with no numerical
AI share inferred. FloatLib is not a quality calibration anchor.

The initial run reuses the clean `~/FloatLib` sources and the matching compiled
dependency from `~/TorchLean/.lake/packages/floatlib`. An isolated copy in
`/tmp/floatlib-analysis/repo` supplies seven missing compiled modules; no source
changes are required. All 1,289 selected modules are explicitly imported,
including optional modules outside the default umbrella import.

The exact graph retains 15,691 declarations and 769,173 edges across 1,216
modules. Its file statistics cover 172,991 code lines. The other 73 modules
have no declarations retained under the existing contraction rules; their
1,238 code lines are included in the full-source and Git counts. Source
metadata joins to 90.20% of retained declarations.

M13 (elaboration cost) is unavailable: no elaboration benchmark was run.
Source-derived metrics retain the existing parser's limitations. Exact graph
coverage, source metadata joins, dependency revisions and the dump checksum are
recorded in [measurement metadata](../results/floatlib_measurement.json).

M17 uses the same pinned source revision and full Git history. It counts
174,229 source code lines across 1,289 files, of which 174,084 (99.92%) are
attributed to the Git identity displayed as **Robert joseph**, including its
`robert` alias. Richard Beauchamp accounts for the remaining 145 lines. These
are current-line Git attributions, not a measure of actual maintenance duties
or who generated the code. See [the metric definition](author-concentration.md).

## Reproduce

Use a clean checkout at the recorded revision. For a fresh checkout, obtain its
pinned dependencies and Mathlib cache with `lake update` and `lake exe cache get`
before the steps below. Run the commands from this analysis repository, with
`FLOATLIB_REPO` pointing to that checkout. Builds modify the chosen checkout;
use a temporary clone to preserve an existing one.

```bash
set -euo pipefail
export FLOATLIB_REPO=/tmp/floatlib-analysis/repo
export FLOATLIB_WORK=/tmp/floatlib-reproduction
python3 - <<'PY'
import json, os, subprocess
from pathlib import Path
from lean_reuse.graphbuild import collect_files
from lean_reuse.repos import REPOS

repo = Path(os.environ['FLOATLIB_REPO']).resolve()
work = Path(os.environ['FLOATLIB_WORK']).resolve()
work.mkdir(parents=True, exist_ok=True)
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo)
revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
assert revision == 'acba2057e452f32f4ed4f06bb0adbeda5342ba92'
spec = REPOS['floatlib']
files = [rel for _, rel in collect_files(str(repo), spec['roots'])]
modules = [rel[:-5].replace('/', '.') for rel in files]
(work / 'modules.txt').write_text('\n'.join(modules) + '\n')
# Explicit targets also build optional modules absent from the umbrella import.
subprocess.run(['lake', 'build', *['+' + m + ':olean' for m in modules]], cwd=repo, check=True)
assert all((repo / '.lake/build/lib/lean' / (m.replace('.', '/') + '.olean')).is_file()
           for m in modules)
prefix = Path(subprocess.check_output(['lake', 'env', 'lean', '--print-prefix'], cwd=repo, text=True).strip())
targets = {'floatlib': repo, 'mathlib4': repo / '.lake/packages/mathlib',
           'batteries': repo / '.lake/packages/batteries', 'aesop': repo / '.lake/packages/aesop',
           'lean4/src': prefix / 'src/lean'}
for name, target in targets.items():
    assert target.is_dir(), target
    link = work / 'sources' / name
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() or link.is_symlink():
        assert link.resolve() == target.resolve(), link
    else:
        link.symlink_to(target, target_is_directory=True)
(work / 'manifest.json').write_text(json.dumps({'floatlib': {
    'repo_dir': str(repo), 'url': spec['url'], 'roots': spec['roots'], 'revision': revision}}))
PY
python3 -m lean_reuse.run_all --repos-dir "$FLOATLIB_WORK/sources" \
  --cache-dir "$FLOATLIB_WORK/cache" --only core,batteries,aesop,mathlib4,floatlib \
  --force --nproc 4 --out "$FLOATLIB_WORK/textual.json"
python3 -m lean_reuse.extract_runner --repo-dir "$FLOATLIB_REPO" \
  --imports "$(paste -sd, "$FLOATLIB_WORK/modules.txt")" --full-prefixes FloatLib --dyn \
  --out "$FLOATLIB_WORK/floatlib.tsv" --scratch "$FLOATLIB_WORK/dumps"
python3 -m lean_reuse.envdump --dump "$FLOATLIB_WORK/floatlib.tsv" --repos floatlib \
  --textual-cache-dir "$FLOATLIB_WORK/cache" --out-cache-dir "$FLOATLIB_WORK/cache_env"
python3 -m lean_reuse.run_all --repos-dir "$FLOATLIB_WORK/sources" \
  --cache-dir "$FLOATLIB_WORK/cache_env" --only floatlib --skip-build \
  --out "$FLOATLIB_WORK/env.json"
python3 -m lean_reuse.validate_tiers --textual-cache-dir "$FLOATLIB_WORK/cache" \
  --env-cache-dir "$FLOATLIB_WORK/cache_env" --out "$FLOATLIB_WORK/validation.json"
python3 -m lean_reuse.author_concentration --manifest "$FLOATLIB_WORK/manifest.json" \
  --only floatlib --out "$FLOATLIB_WORK/authorship.json" --cache-dir "$FLOATLIB_WORK/blame-cache"
```

Merge only FloatLib's new rows, then generate the local dashboard:

```bash
python3 - <<'PY'
import json, os
from pathlib import Path
work = Path(os.environ['FLOATLIB_WORK'])
for name, incoming in [('results_env.json', 'env.json'), ('results_textual.json', 'textual.json'),
                       ('validation.json', 'validation.json'), ('author_concentration.json', 'authorship.json')]:
    path = Path('results') / name
    data = json.loads(path.read_text())
    data['floatlib'] = json.loads((work / incoming).read_text())['floatlib']
    path.write_text(json.dumps(data, indent=1) + '\n')
PY
python3 report/make_report.py --env results/results_env.json \
  --textual results/results_textual.json --validation results/validation.json --out docs/index.html
cp docs/index.html results/report.html
```

Update the measurement metadata when remeasuring. TorchLean's existing FloatLib
references remain in its external `other` bucket, preserving that measurement.
