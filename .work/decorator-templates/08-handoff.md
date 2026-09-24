# M08 implementation verification handoff

Status: implementation complete; independent Astra review pending. Agent `/root/m08_implementation`, `gpt-6-astra`, high reasoning. No commits made by this agent. Coordinator owns checkpoint commits, status, and review records.

## Baselines and boundaries

Clean IoC started at `18183923a4199daa6c4471f737a82da3d09bb153`, with the coordinator's execution log and unrelated untracked `.work` planning files preserved. No Clean IoC production code, tests, public documentation, or examples changed. This handoff is the sole implementation-owned Clean IoC change. No portable defect regression was necessary because the local proof found no Clean IoC defect.

Bark-core started clean on `v1_rc` at `b0cd55693889785a14be128d1f78f815f2a6e5fe`. Its HEAD remains exactly that commit. All changes below remain local and uncommitted; do not commit them. No unrelated changes were reset. These internal notes are not source material for public documentation.

## Delivered behavior

- A shared explicit OperationHandler service group receives ordinary handler registrations, generated saga handlers, and deferred data-protection discovery contributions. No central list of eight handler service origins remains in transaction policy composition. A new compatible handler family participates solely by contributing its registration to that group.
- SQLAlchemy and DynamoDB install independent family-filtered templates, each once per builder/boundary through existing run-once bundles. Each source injects its exact registration ID, retaining resource-name filters, scoped lifespans, coordinator identity and existing decorator positions. Database bundles no longer install per-UoW policies or repeat per-service decorator registration. SQLAlchemy's generated inherited generic source specialization remains intact. DynamoDB family matching includes configured subclasses.
- Existing per-source condition parameters remain supported as local static metadata on generated source implementation classes. DynamoDB generates a configured subclass only when its condition parameter is supplied. The normal DynamoDB source remains the existing concrete class. This is local migration wiring, not a proposed new Clean IoC API.
- Explicit custom-UoW policy bundles now retain one `DecoratorTemplateRegistration` handle rather than eight ordinary decorator handles. Application/saga tests intentionally migrate customization to template patching; ordinary saga retry/query-ID handles remain ordinary decorator IDs. As with existing run-once semantics, retain the policy instance that actually installs the policy when customization is needed.
- Coverage markers record template IDs. Coverage requires a matching *selected frozen source decision*, so removing a template or rejecting its source cannot leave a stale marker that falsely satisfies coverage. A selected policy may deliberately reject a target via `when`, disable marker, or explicit nonmembership. The tests prove those exclusions separately from policy absence.
- SQLAlchemy write-safety classification now recognizes nominal OperationHandler ancestry instead of the closed service-origin list. It covers custom families, concrete aliases, nonmembers, opted-out handlers and explicit `when` exclusions independently of decoration. All original lifespan, coordinator, boundary-order, exact-resource ownership, overlap, orphan, transaction-control and partial-resource checks remain enabled. Four existing expected diagnostic counts deliberately increase from one to two because both the registered service and its concrete handler alias now receive validation; error codes and safety assertions remain intact.

## Task-owned bark-core ledger

Production files (6):

1. `bark_core/application/decorator_composition.py` — shared explicit group and retained template handle.
2. `bark_core/application/bundles.py` — ordinary/deferred group contributions.
3. `bark_core/application/sagas/bundles.py` — saga group contributions.
4. `bark_core/unit_of_work/bundles.py` — generic templates, backend source filters, active-policy evidence, nominal safety classification.
5. `bark_core/db/bundles.py` — one shared SQLAlchemy family policy; preserve source conditions and session binding.
6. `bark_core/aws/bundles.py` — one shared DynamoDB family policy; preserve source conditions and connection binding.

Tests (6):

7. `tests/unit/bundles/test_application.py` — explicit direct-registration membership and migrated template editing.
8. `tests/unit/bundles/test_sagas.py` — migrated per-family target exclusion through template editing, preserving order checks.
9. `tests/unit/bundles/test_unit_of_work.py` — account for service plus concrete-alias safety diagnostics.
10. `tests/unit/bundles/test_decorator_templates.py` — new 14-case bounded local proof.
11. `tests/unit/bundles/test_outbox.py` — subprocess import probe preserves caller PYTHONPATH.
12. `tests/unit/bundles/test_outbox_sqlalchemy.py` — same subprocess environment fix.

The last two changes are test infrastructure only: their subprocesses previously replaced PYTHONPATH with the bark checkout, accidentally selecting installed Clean IoC b12. They now prepend that directory and retain the caller's override. No dependency declaration, lockfile, installed package, virtual environment, persistent environment setting, external database, or remote service was changed. Temporary editing helpers were outside both repositories in `/tmp`; none is part of the deliverable.

## Verification

Every bark test process used `PYTHONPATH=/Users/peter.daly/WS/pete/clean_ioc` and bark's existing `.venv/bin/python` (Python 3.14). The directly verified import is `/Users/peter.daly/WS/pete/clean_ioc/clean_ioc/__init__.py`; installed package metadata is not the evidence. The b14 project pin and installed environment remain unchanged.

- Migrated four-file baseline: **110 passed in 8.95s** (`tests/unit/bundles/test_application.py`, `test_unit_of_work.py`, `test_sqlalchemy.py`, `test_sagas.py`).
- New bounded proof: **14 passed in 1.50s**. Four parametrized mixed-backend cases use two named databases with the *same* inherited generic session specialization, two real isolated in-memory SQLite engines, and a mocked DynamoDB session. Both source/template declaration orders verify distinct sessions, exact UoW instances and the shared scoped coordinator. Success persists one row in each SQLite database; failure leaves both empty and calls only DynamoDB rollback. Other cases cover group versus DerivedServices, custom family, late data-protection discovery, removed/source-disabled policies, target conditions, disable markers, nonmembers, sessionless members, and independent write-safety rejection.
- Expanded rerun: **409 passed in 41.00s**, using `PYTHONPATH=/Users/peter.daly/WS/pete/clean_ioc .venv/bin/python -m pytest tests/unit/bundles tests/unit/application/data_protection/test_clean_ioc.py -q --disable-warnings --maxfail=3`. The first expanded run was **406 passed, 2 failed**, with both failures caused solely by subprocesses discarding the import override; the final run includes the two fixes and the added sessionless case.
- Bark changed-file static checks passed on exactly all 12 Python files listed in the ledger: `.venv/bin/ruff check <12 files>`, `.venv/bin/ruff format --check <12 files>` (12 already formatted), and `PYTHONPATH=/Users/peter.daly/WS/pete/clean_ioc .venv/bin/pyright --pythonpath .venv/bin/python <12 files>` (0 errors/warnings). An initial pyright invocation without the explicit interpreter could not discover environment dependencies; the final explicit-interpreter invocation is the relevant result. Both repositories passed `git diff --check`. Bark final status is precisely 11 modified tracked files plus the new untracked test file listed above; HEAD remains the baseline, with no task-created commits.
- Clean IoC `make ci`: passed; **735 tests passed in 6.35s**, Ruff, format, ty, documentation example validation and benchmark discovery all passed. One existing Starlette/httpx deprecation warning. No public documents/examples were edited.
- Clean IoC `make pre-commit`: passed all four hooks (actionlint, Ruff, ty, full tests).
- No new Clean IoC implementation changed, so earlier milestone behavior was exercised by the full existing suite rather than a new regression. This M08 run uses Python 3.14; the full supported-version matrix remains M10 work.

## Limits and review focus

No MySQL/LocalStack or other external-service integration tests ran. The outbox integration fixture was inspected: it creates/drops a random database through an admin URI and configures LocalStack, so it was excluded. SQLite evidence is genuine local transaction integration; DynamoDB evidence proves lifecycle calls through mocks, not AWS transactions or distributed atomicity. Bark's full integration suite, API snapshot/compatibility release guards and all-repository static jobs are not claimed passed for this intentionally uncommitted experiment.

Review the complete bark diff and the new untracked test file, especially active-marker/source evidence, explicit nonmember semantics, static source-specific condition metadata, exact source identity, nominal safety coverage and unchanged ownership validation. The compiler has not been modified in M08. Fresh independent Astra review and coordinator implementation checkpoint are still required; this handoff claims neither review acceptance nor milestone completion.

## Final gate record

Accepted by `/root/m08_review` Astra High;409 independent tests plus closed-generic source probe, no findings. Search `1818392`; verification `0f63ace`; review `827964d`. All commit hooks passed. No public docs changed; no reader gate applies. All12 local bark ledger files remain uncommitted at original HEAD; no dependency/env edits. M09 author must not read or use this integration record or bark code; use standalone Clean IoC material.

## Verified checkpoint index

Coordinator completion audit; gate hashes resolve to local commit objects. The final M10 hash is filled after its commit.

| Gate | Outcome | Local commit |
| --- | --- | --- |
| Search | Passed | `1818392` |
| Implementation verification | Passed | `0f63ace` |
| Independent technical review | Passed | `827964d` |
| Final handoff | Passed | `2ba08f2` |
