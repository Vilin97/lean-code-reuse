# Git author concentration (M17)

For each project, count surviving Lean code lines attributed to each Git author
identity. Report the largest author's line count and that count divided by all
analyzed code lines. This describes concentration and its absolute scale; it does
not measure maintenance responsibility, original authorship, knowledge, review
coverage, or the percentage written with AI.

The dashboard adds two ranking graphs and a sortable table under **Author
concentration**. M17 is deliberately excluded from PCA, the composite quality
score, and the Architecture Index. A concentrated project is not automatically
poorly written.

## Measurement rules

- Use all tracked `.lean` files under each project's `REPOS[key]['roots']`,
  respecting `EXCLUDED_DIR_PARTS`. Dependencies and examples/tests outside these
  roots are excluded. File roots and directory roots are supported, without
  double counting overlapping roots.
- Read sources from a pinned commit, ignoring working-tree changes. Use the
  existing source parser's line definition: lines remaining nonblank after
  comments and string/character literals are stripped, preserving line numbers.
- Run `git blame --line-porcelain -w -M --ignore-revs-file= REV -- FILE`.
  Ignore whitespace-only edits, follow whole-file renames and detect moves within
  a file. Cross-file copy detection is not enabled. Ignore-revision lists from
  local Git configuration are cleared for reproducibility.
- Use the pinned commit's `.mailmap`, then group by normalized author email.
  Display the name attributed to the most lines within that identity, with
  deterministic tie-breaking. Preserve aliases and tied top identities in the
  data. Different identities with the same display name remain separate.
  Unmapped email aliases can split one person across identities, and a shared
  account can combine several people. The metric reports the identities Git can
  establish, not a verified count of individual humans.
- When an author has no email, group by their exact recorded name and explicitly
  report `name_only_sloc` and `identity_basis: name_only`. This is weaker identity
  evidence. Public output contains hashed identity IDs rather than emails.
- Keep bots and template identities in the denominator. Git attribution does not
  divide lines among co-author trailers or reviewers. Imported, regenerated,
  squashed, and mass-refactored code may be attributed to the person recording it.
- Require complete Git history and attribution for every selected code line.
  Shallow repositories or failed files produce an error, not a partial percentage.
  A comments-only scope has zero code lines and no top author/share.

## Scope and snapshot differences

The original graph results do not include source revision and file manifests for
most projects. Author concentration therefore has **its own pinned snapshot,
file list, and denominator**, stored in `results/author_concentration.json`.
It is not assumed to describe exactly the same revision as the older graphs.

The source scan also includes every registered library file, whereas the exact
declaration graph can omit files without retained declarations or use a sample.
In particular, ATLAS, superhuman, and Seed-Prover attribution covers their
registered source roots rather than the graph's buildable/sample subset. These
files do not need to compile for Git attribution.

TorchLean's full registered library has 977 files and 196,434 code lines at
`bb95db148ab63e3beb3e9c43813ad782bdddad67`; Robert's identity has 196,303 of those
lines (99.93%). The earlier graph represented 969 files and 196,308 code lines;
restricting attribution to that subset gives Robert 196,177 lines. The 126-line
difference comes from the eight library files without retained declarations.

## Reproduce

Full Git history is required, but neither Lean nor library builds are needed.
Bare repositories work. Existing local checkouts are only read. For a shallow
checkout, fetch its full history before measuring; the collector refuses to infer
authorship at an artificial shallow boundary.

Create a manifest mapping project keys to local Git repositories, source roots,
and immutable revisions. For example:

```json
{
  "torchlean": {
    "repo_dir": "/home/roland/TorchLean",
    "url": "https://github.com/lean-dojo/TorchLean",
    "roots": ["TorchLean"],
    "revision": "bb95db148ab63e3beb3e9c43813ad782bdddad67"
  }
}
```

The exact revisions, URLs, and roots for the published measurement are in the
results file. Clone each URL without `--depth`, then create a local manifest from
those fields. If `revision` is omitted, the CLI pins each repository's HEAD at
the beginning of the run.

```bash
python3 -m lean_reuse.author_concentration \
  --manifest /tmp/author-manifest.json \
  --out results/author_concentration.json \
  --cache-dir /tmp/lean-authorship-work/cache \
  --repo-workers 2 --file-workers 4

python3 report/make_report.py \
  --env results/results_env.json \
  --textual results/results_textual.json \
  --validation results/validation.json \
  --authorship results/author_concentration.json \
  --out docs/index.html
cp docs/index.html results/report.html
```

The collector checkpoints each completed repository and caches file attribution
by revision, file, method, source lexer version, and Git version. Rerunning resumes
from those file caches. Use `--only torchlean,mathlib4` to retry selected projects;
other result entries are preserved. Any requested project failure returns a
nonzero exit status and an explicit error row.

The initial 26-project run covered 79,335 files and 18,020,265 source code lines.
The complete-data report was checked in a headless browser for both ranking
graphs, all 26 rows, sortable counts, and JavaScript errors.

Report generation automatically loads `author_concentration.json` beside the
environment results when `--authorship` is omitted. Missing measurements remain
visibly unavailable; they never become zero-percent results.
