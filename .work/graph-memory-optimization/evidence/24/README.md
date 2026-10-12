# Task 24 verification evidence

This directory records correctness and API migration, not performance acceptance.

- `task-relative.patch`: changes since the accepted task-23 working tree, including root's packaged-guide and benchmark-driver edits. It is not a diff from Git HEAD alone: tasks 20–23 were already uncommitted.
- `start-source-hashes.json`: immutable 292-file task-start snapshot identity. `start-extra-source-hashes.json` adds unchanged-at-start project/docs configuration from HEAD `34d1ea02840afe6f23f0693b32651028ec7d9128`.
- `changed-source-hashes.json`: 159 changed files with exact before/after hashes. `source/` contains their final contents.
- `final-source-hashes.json`: all 295 captured source/documentation files. `final-package-hashes.json` separately freezes the installed package's source.
- `unchanged-fixture-hashes.json`: 13 unchanged HEAD files (`uv.lock` and executable example applications) required by the full reconstructed test suite.
- `reconstruction-import.json`: resolved import proof from the isolated reconstructed copy.
- `check-results.json`, `checks/`: supported-Python CI, pre-commit, strict docs, executable examples, FastAPI compatibility and functional helper results.
- `retired-drivers/`: exact historical source of ten obsolete independent-toggle experiments, with hashes.
- `consumers/`: isolated Bark/Cop source patches, actual source/import hashes, unchanged-original proofs and complete correctness verification (separate root-owned annex).

## Reproduction

The original task-start snapshot is `/tmp/clean-ioc-task24-start`. The verified reconstruction is `/tmp/clean-ioc-task24-reconstructed` (macOS resolves `/tmp` to `/private/tmp`). Reconstruct from a source tree matching the start manifests, apply `task-relative.patch`, supply the unchanged fixture files from the recorded HEAD, then check every final source hash. Do not apply the patch directly to plain HEAD without the accepted earlier task changes.

For the current workspace:

```sh
make ci
uv run pre-commit run --all-files
uv run mkdocs build --strict
```

`make ci` runs lint, format, ty, all tests, executable examples and **BenchBro discovery only**. It does not execute benchmark measurements.

The supported-Python lanes used separate frozen-lock environments:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/clean-ioc-task24-py311 uv sync --frozen --python 3.11 --group dev
UV_PROJECT_ENVIRONMENT=/tmp/clean-ioc-task24-py311 make ci
# Repeat with py312 / 3.12 and py313 / 3.13. Workspace .venv uses Python 3.14.4.
```

The isolated reconstruction uses the existing dependency interpreter with `PYTHONPATH` pointing to the reconstructed source and its working directory set there. Verify `Path(clean_ioc.__file__).resolve()` is inside the reconstructed directory before running `python -m pytest -q`. The first setup omitted `uv.lock` and example applications; those harness omissions were corrected from unchanged HEAD files before the complete rerun. No package edits were needed.

FastAPI compatibility used separate Python 3.12 frozen-lock environments followed by `uv pip install --python <environment>/bin/python 'fastapi==0.121.0'` or `--upgrade 'fastapi<1'`, then `python -m pytest -q tests/ext/fast_api`. This preserves the workspace lockfile and ordinary environment. Resolved versions are in `check-results.json`.

No memory/timing/population comparison was run. Historical measurement driver bodies were not exercised. Actual measurement acceptance, including native/Docker comparisons, remains task 25. The source-coupled artifact codec remains a parked unsupported experiment.
