# Task 04 rollback

Date: 2026-10-09\
Status: Reverted and verified; all changes remain local and uncommitted.

The maintainer requested undoing task 04. Although it reduced retained Python
allocations from 38.43 to 35.77 MiB, measured process RSS increased from 131.89 to
135.17 MiB, allocation peak increased slightly and graph inspection slowed.
The original KEEP recommendation did not match the goal of reducing application
process memory and has been superseded.

## Restored scope

- Remove the subtree-sharing pass, projection/context record classes and helper.
- Restore the memory runner's pre-task-04 census and source inventory.
- Restore the experimental artifact codec to schema 5, including the richer
  template/provider/map support that existed before task 04.
- Remove the task-04-only tests, prototype and probes from executable discovery.
- Keep tasks 01 and 02, task 03's audit/tests, the richer memory fixture and the
  artifact experiment with their original raw results.

The restored files match the hashes in `evidence/04-before.json` and
`evidence/artifact-post02-rich.json`: `clean_ioc/components.py`, `container.py`,
`tooling.py`, `selection_census.py`, and the fixture, memory runner, artifact codec
and both artifact runners. This confirms that rollback preserves the earlier
implementations rather than resetting the worktree to its older Git HEAD.

## Preserved history

The [original results](04-result.md), intermediate comparisons and all raw JSON
measurements remain intact. The removed helper, tests, prototype and three probes,
plus the task-04 versions of modified source files, are archived as `.py.txt`
files under `evidence/04-reverted-source/`. Its [manifest](evidence/04-reverted-source/manifest.json)
records original paths and SHA256 hashes. These snapshots are reference material,
not active Python modules or tests.

## Verification

- **2,079 tests pass**, including the earlier shared-definition, captured-fact,
  escaped-callback, reachability and artifact round-trip coverage. The 25 removed
  cases belonged only to the reverted task-04 representation.
- Ruff lint/format, type checking, executable documentation examples, benchmark
  discovery and whitespace checks pass.
- Strict MkDocs retains its eight pre-existing outside-docs link warnings; the
  existing FastAPI/Starlette test warning also remains.
- [Source verification](evidence/04-rollback-source-check.json) confirms the exact
  pre-task-04 hashes of the nine files identified above and all archived snapshots.
- A [fresh-process load](evidence/04-rollback-artifact-load.json) of the original
  post-task-02 eight-route artifact passes unchanged. Its SHA256, graph fingerprint
  and resolution validation match the saved artifact experiment. Schema 5,
  88,558 physical records, 124 workers, 26 managed scopes and 64 async source-map
  calls are preserved; compilation is disabled and template callback counts are zero.

The artifact load is a functional compatibility check, not a new repeated memory
comparison. No new memory-saving claim is made from this rollback; the earlier
measurements remain the evidence for the restored source state.
