# Task 22 — Avoid analysis-only evidence construction

Date: 2026-10-10. Implementation complete; scoped coordinator review accepted. No commit, push, release, deployment, consumer edit or performance measurement.

Coordinator review inspected producer guards, raw provenance and its materialization, nested operation isolation, callback snapshots and failure coverage. The review-found located-rule provenance regression was corrected with an exact-origin regression test. All 54 source/patch hash entries match the reviewed workspace. Task 23 still owns optional instrumentation and Composition; task 24 owns full migration and consumer acceptance.

Build now avoids candidate/history, explanation, template decision, origin-index and partial-failure evidence at their producers, including registration preparation and source subcompilers. Rule registration does not enable capture. Analysis materializes full original provenance and records callback decisions once. Raw immutable declaration facts remain because callers select build versus analysis later; source capture preserves declaration-time locations without retaining frames and tolerates an unavailable working directory. The [reader inventory](22-inventory.md) records retained facts and the task 23/24 boundaries.

- **337 focused tests passed**, both in the working tree and an isolated task-relative patch reconstruction: task 21's 294 checks, 28 new capture/provenance regressions, eight template tests and seven snapshot cases. [Commands](evidence/22/verification.json), [live log](evidence/22/pytest-final.log), [reconstruction](evidence/22/reproduction.json), [reconstructed log](evidence/22/reproduced-pytest.log).
- Lint, formatting and type checks passed for the changed source/tests. [Lint](evidence/22/ruff-final.log), [format](evidence/22/format-final.log), [types](evidence/22/ty-final.log).
- **Both unchanged real Bark validators passed:** build invokes neither; analysis invokes each once. All three existing UoW/SQL fixtures preserve expected findings. The proof adapts only obsolete registration phase syntax and records actual imports/hashes. [Proof](evidence/22/bark-rules-correctness.json).

Eight existing test functions in **two files** moved from obsolete private `_build` calls to the applicable `build()` or `analyse()` operation. Their template decisions, exact provenance, snapshot, cleanup and census assertions remain. This narrow migration is recorded in the patch; whole-suite migration remains task 24. An earlier expanded run exposed these obsolete calls; its log is retained. Preliminary passing package records are preserved with `-initial` names; the unqualified final records are authoritative.

The final patch reconstructs all six changed/new files byte-for-byte and verifies all 47 package Python files against this workspace. Constructor sentinels demonstrate absent forbidden allocations for tested execution paths; they do not measure object populations. Optional instrumentation still uses task 21's rich bridge, and the public Composition API remains task 23 work. No whole-suite, full feature-allocation or performance acceptance is claimed.

## Identity and reproduction

- Pre-task compiler SHA-256: `d99aa4edbd26d70b908dec17632d0353e66df62c763695a3941f5e5d2a641760`.
- Final compiler SHA-256: `5f610d45def38d9c536bb557650a1dd70d50eb721c0a32a3fd481f351c04f51b`.
- [Task-relative patch](evidence/22/task22.patch) SHA-256: `b55b60637254d07c7a1ec465933c7875909a582f28362626da40a418490407bd`.
- [Before/after and supporting hashes](evidence/22/source-manifest.json), [source locations](evidence/22/source-symbols.json).

Run `.venv/bin/python .work/graph-memory-optimization/evidence/22/verify.py` for the focused correctness and quality checks. The [packaging script](evidence/22/package_evidence.py) documents reconstruction from task 21's already verified temporary source tree plus this patch, using the preserved dependency environment; it refuses to overwrite an existing patch. To rerun tests in the recorded reconstruction, use the exact command, working directory and `PYTHONPATH` in [reproduction.json](evidence/22/reproduction.json).

Only small source/test copies were made for reconstruction. Historical baselines, environments and earlier evidence are preserved. All timing, memory, retained-owner/temporary-overlap costs and population comparisons remain deferred to task 25.
