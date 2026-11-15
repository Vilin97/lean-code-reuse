# TorchLean Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add TorchLean to the exact-tier corpus and regenerate the local dashboard with real measurements.

**Architecture:** Register the library in the existing Python pipeline, build a pinned upstream checkout, and extract every library module. Merge the new results into the committed corpus without changing other repositories' measurements.

**Tech Stack:** Python, NumPy, Lean/Lake selected by TorchLean's toolchain.

**Spec:** The integration outline in this conversation, approved by the user with “yes, do that.”

## Global Constraints

- Measure only `TorchLean/`; exclude examples, tests, and dependencies from self declarations.
- Use exact environment extraction for the dashboard; textual results supply source metadata and cross-checks.
- Record the upstream commit and toolchain for reproducibility.
- Keep FloatLib in the existing external `other` bucket.
- Initially use unspecified provenance until evidence is established; do not add TorchLean to quality calibration sets. Follow-up: the pinned contribution guide discloses AI assistance, so provenance is now Human + AI mix (group 1).
- Preserve all existing result entries; do not publish the dashboard.
- Store downloaded repositories, caches, dumps, and build logs in `/tmp/lean-reuse-work`.

## Review Focus

- Missing root module: enumerate all built library modules and verify coverage against source files.
- Extraction failure: return a failing process status, never publish an empty or stale dump.
- Path handling: use absolute output/scratch paths because Lean runs in the target checkout.
- Missing dependency caches: build real upstream source metadata or explicitly construct source metadata from the pinned dependencies.
- Corpus preservation: compare all old JSON entries before and after merging.

### Task 1: Registration and extraction entry point

**Files:** `lean_reuse/repos.py`, `lean_reuse/envdump.py`, `report/make_report.py`, `report/template.html`, `lean_reuse/extract_runner.py`, `lean_reuse/parser.py`, `tests/test_extract_runner.py`, `tests/test_parser.py`.

**Interfaces:** Existing registry key `torchlean`; `run_extract(..., dyn=True)` exposed through the CLI.

- [x] Add focused subprocess tests for dynamic extraction, output path handling, and failing Lean exit status; observe failures before implementation.
- [x] Register TorchLean, enable the dynamic extractor CLI, and run the focused tests.
- [x] Confirm the existing report still builds without a TorchLean result.

### Task 2: Measure and integrate

**Files:** `results/results_env.json`, `results/results_textual.json`, `results/validation.json`, `results/torchlean_measurement.json`, `docs/index.html`, `results/report.html`, `README.md`.

**Interfaces:** Existing `graphbuild`, `envdump`, `run_all`, `validate_tiers`, and `make_report` tools.

- [x] Reuse the clean, fully built `~/TorchLean` checkout supplied by the user; record its revision and verify its pinned dependencies and module coverage.
- [x] Create source caches, enumerate all built library modules, extract and convert the exact graph.
- [x] Check module coverage, source join quality, and external attribution; compute metrics and validation.
- [x] Merge only TorchLean entries, regenerate both report artifacts, and document reproducible commands.
- [x] Verify old entries are unchanged and TorchLean appears exactly once in the report data.
- [x] Run focused tests and obtain a final independent code review.

## Completion evidence

- Four focused tests pass, including the public/meta import regression discovered during measurement.
- All 977 library modules loaded; 16,622 declarations retained across 969 modules.
- All original corpus result entries preserved; both generated report artifacts match.
- Reproduction setup independently discovers the same module list; shell/Python and generated JavaScript syntax checks pass.
- Independent review found no Critical or Important issues.
- M13 is unavailable because the optional elaboration benchmark was not run.
- Browser smoke test was unavailable because the installed Firefox Snap cannot launch in this sandbox; report data and chart inclusion logic were checked.
- Work remains as a local, uncommitted diff; no publishing performed.
- Follow-up: corrected authorship from Unspecified to Human + AI mix using the maintainers' AI usage disclosure at the measured revision; this is self-reported, not inferred from quality metrics.
