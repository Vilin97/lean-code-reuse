# Author Concentration Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Measure the largest author's current Git-attributed Lean code line count and percentage for all 26 dashboard repositories, and display the results.

**Architecture:** A standalone Git collector reads pinned source blobs and blame attribution, using the existing source-line counter. A separate results file feeds an additional report section without changing existing graph metrics, PCA, or composite scores.

**Tech Stack:** Python standard library, Git, existing Python/JavaScript report generator.

**Spec:** The user approved the definition in the conversation and explicitly requested implementation and computation for all 26 projects. Largest author = person with most surviving analyzed code lines; share = their lines / all analyzed code lines.

## Global Constraints

- Library scope follows each repository's registered roots and directory exclusions; dependencies, examples, and tests outside those roots remain excluded.
- Pin and record every measured revision and file list. The existing 25 older graph snapshots lack revision/file manifests, so Git results have their own explicit denominators and scope, including full registered roots for sampled graph corpora.
- Count code with the existing lexer, preserving original line numbers; attribute with `git blame --line-porcelain -w -M`.
- Normalize identities using mailmap and author email, preserving name aliases. Do not publish email addresses. Do not infer AI origin or actual maintenance responsibility.
- Reject shallow history and report failed or missing measurements explicitly; never silently publish partial counts as complete.
- Cache each file's result with revision, method, and identity mapping inputs so long runs can resume.
- Preserve existing uncommitted integration work, existing graph results and scores. Work in the current authorized writable workspace; Git metadata is read-only. No commits or publishing.
- Store downloaded histories and temporary measurements under `/tmp/lean-authorship-work`.

## Review Focus

- Deleted lines, comments, strings, and whitespace-only edits must not inflate or reassign the source-code count.
- Author aliases, mailmap entries, different people with the same display name, and deterministic ties.
- Missing paths, shallow histories, failed blame operations, and cache invalidation must not masquerade as complete data.
- Source snapshots and denominator differences from graph samples must be visible in the report.
- Git-sourced names must be escaped in HTML, and new data must not affect PCA or composite scores.

### Task 1: Git collector and measurement

**Files:** `lean_reuse/author_concentration.py`, `tests/test_author_concentration.py`, `results/author_concentration.json`.

**Interfaces:** `measure_repo(repo_dir, roots, revision='HEAD', *, workers=4, cache_dir=None)` returns complete metadata, author rows, largest-author count/share, and coverage; CLI accepts `--manifest`, `--out`, `--cache-dir`, `--repo-workers`, `--file-workers` and checkpoints after each project.

- [x] Write real temporary-Git tests for attribution after edits/deletion, whitespace, aliases/mailmap, source filtering, pinned revision reads, empty scope and shallow refusal.
- [x] Observe failures, implement collector, and run the full suite.
- [x] Acquire complete histories, pin 26 revisions, run measurements with bounded concurrency, and inspect counts/coverage.

### Task 2: Report and reproducibility

**Files:** `report/make_report.py`, `report/template.html`, `tests/test_author_report.py`, `README.md`, `docs/author-concentration.md`, `docs/index.html`, `results/report.html`.

**Interfaces:** Optional `--authorship` JSON input, additive `author_concentration` payload. Report includes largest-author percentage and line-count graphs plus sortable details including source denominator, scope, revision and date.

- [x] Add a report regression test proving Git data appears without changing PCA/composite inputs or results, and unavailable data remains unavailable.
- [x] Implement the report section, explain interpretation and reproduce commands, regenerate artifacts.
- [x] Verify all 26 results, preserved old metrics, complete test suite, generated JavaScript syntax, and report rendering where available.
- [x] Obtain one independent final review, address material findings, and report measured results and elapsed time.

## Progress

- Baseline: 4 existing tests pass.
- Ruling: Continue in the existing writable workspace rather than create a new Git worktree; this preserves the user's earlier uncommitted TorchLean integration and respects read-only Git metadata.
- Ruling: Author concentration is descriptive and excluded from PCA/composite quality scores; attribution concentration is not itself a quality grade.
- Ruling: Measure current pinned registered library roots separately from the older graph samples because their original revision/file manifests are unavailable.
- Source histories downloaded in full for 23 missing projects; reused local Mathlib, CSLib, and TorchLean. All 26 registered source scopes exist at their selected revisions.
- Collector and report tests: 14 passing, with observed failures before implementation/fixes. Generated JavaScript syntax passes.
- Browser verification on final artifacts: both charts contain all 26 measured projects, all 26 table rows render, exact TorchLean percentage appears, sorting passes, and no page JavaScript errors.
- Final independent review: no Critical or Minor findings; one Important missing-root validation issue. Fixed with `test_one_valid_root_does_not_hide_another_missing_root` RED→GREEN; full suite 14/14. Reviewer additionally verified pinned mailmap isolation, deterministic ties, and failed-blame rejection. Declined-to-judge list empty.
- Real-data edge case: empty author email from a Lean editor template. Name-only attribution is retained and flagged; a regression test covers it.
- Completed all 26 repositories: 79,335 files and 18,020,265 SLOC, with all per-author totals, shares, file scopes and revisions verified. Regenerated both matching HTML artifacts.
- Existing environment/textual/validation JSON checksums and original report repository data, PCA, composite, architecture, totals and validation payloads remain unchanged.
- Final full suite: 14/14 passing; Python compilation, generated JavaScript syntax and `git diff --check` pass. The user captured the implementation in WIP commit `b0b26b8` during execution; the completed measurement data, final report artifacts and documentation updates remain local changes. No commits or publishing were performed by the agent.
