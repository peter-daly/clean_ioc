# Task 21 — Direct execution finalization

Date: 2026-10-10\
Status: Core implementation and task 23 warmup/instrumentation/composition integration reviewed and accepted.\
No commit, push, version change, release, deployment or consumer checkout edit.

Coordinator review inspected direct execution finalization, graph/carrier
projection, opaque value preservation, declaration release, cleanup and concurrent
admission. All 54 source/patch hash entries match the final workspace. Accept the
core change for sequential task 22. Task 23 subsequently removed the observer
bridge and supplied public Composition, with 406 focused tests and allocation
sentinels passing; its review closes this feature gate. Full API/consumer migration
remains task 24. No performance acceptance is implied.

Ordinary `build()` now directly emits `_ExecutionPlan`; it does not construct a rich plan, CompiledGraph, report, manifest or full inspection index and discard it. Shared preparation/binding still supplies provider roots, private/deferred selections, decorators/maps, cleanup owners and slots. Selected discovery comes from executable closure. Admitted builders and retained boundary handles release declarations after their last compiler consumers.

Analysis owns its rich graph and a detached execution projection. Runtime creation uses that projection without callback replay, with independent root singleton/preconfiguration state and actual borrowed parent anchors for scope runtimes. Inspection-only boundary failure no longer destroys a completed execution plan; failed primary emission remains unavailable even when retries succeed. Runtime cleanup retains the existing single-error identity and aggregation semantics.

[Inventory](21-inventory.md) records readers, ownership, disposal and the private source seam as they stood at this task's handoff. Warmup target binding uses execution IDs so it can precede inspection compilation. At that handoff, optional instrumentation still used `_observe_execution_bridge` and allocated rich metadata transiently. The reviewed [task 23 result](23-result.md) removes that bridge and certifies the tested instrumented build paths without analysis allocation.

## Verification

- **294 focused tests passed:** the previous task20 262-test proof, 30 new execution/ownership/failure regressions, and the two task17 opaque-finalizer/detached-snapshot regressions. [Commands](evidence/21/verification.json), [log](evidence/21/pytest-final.log).
- **294 passed from an isolated patch reconstruction**, using the preserved task20 source plus only task21's patch. All six changed/new source/test files byte-matched this workspace, and imports resolved to the reconstructed package. [Reproduction](evidence/21/reproduction.json), [log](evidence/21/reproduced-pytest.log). The initial reconstruction path assertion encountered macOS `/var` versus `/private/var` spelling; canonicalized paths fixed the check without any implementation change.
- Ruff lint, format and `ty` passed. [Lint](evidence/21/ruff-final.log), [format](evidence/21/format-final.log), [types](evidence/21/ty-final.log).
- **Both unchanged real Bark validators passed the correctness proof:** build called neither, analysis called each once, and all three existing UoW/SQL policy fixtures retained their expected findings. [Proof and actual import hashes](evidence/21/bark-rules-correctness.json). Only the proof process adapts obsolete registration syntax; consumer files are untouched.

Constructor sentinels cover absent rich finalization on ordinary successful build, including rules and compilation profiling. Other regressions cover private map/decorator/generic discovery, fresh runtime state, borrowed parent cleanup, caller-owned snapshots, opaque map-key identity/no rehash, minimal failure without graph freeze or retry, consumed boundary disposal, concurrent admission and report/read stability. Instrumentation smoke checks disable duration sampling and verify behavior only.

This is not a whole-suite/release acceptance claim. Historical mode/runtime-graph/overlay convenience tests and docs remain task24 migration work; task20 assertions affected by the new owner boundary were migrated to the explicit private source seam, not skipped or weakened.

## Identity and reproduction

- Pre-task compiler SHA-256: `502988d4c3af9faa33577e82e7bd8bde53a7b55c639a6dca01acee43806051d8`.
- Final compiler SHA-256: `d99aa4edbd26d70b908dec17632d0353e66df62c763695a3941f5e5d2a641760`.
- [Task-relative patch](evidence/21/task21.patch) SHA-256: `4e81cc692fd980720c3c7b1a0df36f0cf49152622956e1559b512e1d994fd8a7`.
- [Changed and supporting source hashes](evidence/21/source-manifest.json), [exact source locations](evidence/21/source-symbols.json), before/after source snapshots under `evidence/21`.

Run `.venv/bin/python .work/graph-memory-optimization/evidence/21/verify.py` for the focused correctness/quality checks. `package_evidence.py` records source and reproduces the patch against the already preserved task20 package/tests using its existing dependency environment. It copies only the small package/test source trees to a temporary directory, not environments or historical evidence. The final proof logs and hashes are the records of this task; subsequent tasks must use fresh evidence paths.

All earlier dirty state and historical evidence are preserved. No new benchmark, timing/memory comparison, performance population study, or large baseline/environment copy was run. Retained-owner/temporary-overlap costs and all performance acceptance remain task25 work after tasks21–24 integrate.
