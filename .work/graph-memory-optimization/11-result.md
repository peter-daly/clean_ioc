# Task 11 result — validation and failure ownership implemented

Completed 2026-10-10 by the assigned extra-high-effort task agent. **KEEP** the
scoped lifetime/failure changes; **REFINE/DEFER** further evidence-construction
narrowing. Root review accepted the public run failure boundary and ownership
design. No commit, version bump, push, release or production action was performed.

The [reader/lifetime inventory](11-inventory.md) is the concrete contract and
handoff. Task 10's modes, callback ordering, discovery, overlay and explicit full
validation decisions remain intact. Unknown build rules still receive rich
temporary evidence; validation-only registration never forces that capture.

## Findings and source changes

1. Expiration previously touched only `plan.compiled_graph`. Boundary rules receive
   `replace(graph, ...)`, and warmup replaces the graph again. Saved boundary views
   and the pre-warmup root view remained active, retaining evidence and inspection
   caches after run completion. A shared weak identity registry now expires all
   views of that build. It invokes no graph/application hash or equality, retains
   no graphs strongly, and removes dead entries between repeated analysis passes.
2. Public run failures now retain useful original code/message/path, existing
   structural facts, source provenance where known, and bounded selection witnesses.
   Optional `compiled_graph`, report graph, partial graph, explanations and census
   ownership are released. Saved run inspection views expire on failed validation,
   budget interruption and warmup failure, including failure before a completed plan
   is returned. Failed profiler binding also cleans up the already-issued views.
3. Failure normalization is scoped to errors constructed within this build using
   a context-local ownership marker. Saved foreign analysis errors and their graphs
   remain unchanged even when raised/chained by a run callback. Budget exhaustion
   retains precedence. Python tracebacks and caller-owned builders remain separate
   ordinary owners; debugging frames are not erased by production cleanup.
4. Rule findings capture exact occurrence provenance only with graph-qualified
   identity; foreign/manual findings fall back to the rule declaration. Entrypoint
   and compiler findings retain available origins. SARIF rejects foreign occurrence
   matches and preserves explicit source-free graph override behavior.
5. Diagnostics-off missing selections previously called filtered-out candidates
   "missing declaration". Run failures now capture one representative original
   rejected candidate/reason, or a failing selection callback's candidate/origin,
   without replay. `FailureEvidence.selection_witness` is not full history.
   Triage's additive `attempt_history_available` field explicitly distinguishes
   unavailable history from zero observed attempts; text makes this clear too.
6. The parked artifact encoder excludes/recreates build-local weak ownership.
   This is compatibility maintenance only; no pre-compilation implementation,
   supported artifact surface expansion, or artifact schema/version bump occurred.

Production source changes: `clean_ioc/container.py`, `tooling.py`, `sarif.py`;
parked compatibility: `benchmarks/graph_artifact.py`. New public acceptance tests
are in `tests/test_validation_evidence_lifetime.py`. User documentation is in
`docs/custom-validation.md` and `docs/compiler-tooling.md`.

Reconstructable task-only production differences are
[task11-source.patch](evidence/11/task11-source.patch), with starting source copies,
the full initial working diff and [final hashes](evidence/11/accepted-source.json)
in `evidence/11/`. HEAD remains `34d1ea02840afe6f23f0693b32651028ec7d9128`, branch
`version2`, package `2.0.0rc4`. Every pre-existing dirty change was preserved.

## Validation contract and non-adopted work

Build-mode rules are arbitrary consumers of supported inspection APIs. There is
no sound basis here for inferring narrower requirements, and no measured benefit
justifying a new declaration DSL. No rule is skipped or restricted. The acceptance
item for demonstrated allocation avoidance by narrowed rules is therefore refined:
no narrowed-rule API is adopted and no such saving is claimed. Task 12 can avoid
constructing redundant objects while preserving the same facts.

Analysis and private historical failed-finalization graphs retain their existing
rich inspection contract. Public run now deliberately expires failed views while
preserving original failure facts. The task 06 decorator omission counterexample
still forbids coarse omission for rich rules/analysis. Detached snapshots,
application values, activation-cache ownership and mandatory structural checks
are not weakened. The added scalar error metadata has small construction cost;
this task is not a no-rule compiler allocation optimization.

## Verification

- Final `make ci` passes: Ruff lint/format, `ty`, **2,229 tests**, executable docs
  and BenchBro discovery. The existing Starlette/httpx warning remains.
- **25** new public-mode tests cover root/boundary saved views and bound methods,
  populated caches, budget/no-budget paths, warmup, instrumentation, validation-only
  rules, explicit analysis passes, overlay ancestry, retry, malformed/async/raising
  rules, missing/rejected selection and callback evidence, foreign analysis errors,
  graph-qualified provenance, budget precedence and weak tracking without equality.
- Those 25 tests also pass in isolated Python **3.11, 3.12 and 3.13** environments;
  Python **3.14.4** is covered by full CI. Logs are retained in `evidence/11/`.
- Focused lifetime/artifact/SARIF integration: **108 passed** before the final
  selection-failure-origin test; final CI includes that addition and all fixes.
- Strict MkDocs and `git diff --check` pass. No archived probes were installed or
  reformatted. Full downstream Bark/Cop verification remains task 18.

Intermediate integration failures were fixed: full artifact serialization initially
tried to encode the new lifetime registry; SARIF initially bypassed an explicit
source-free graph; private historical callback-failure tests initially received the
new public-run witness. Final checks cover the corrected behavior, not those failed
intermediate candidates.

## Bounded lifetime evidence

The same [probe](evidence/11/lifetime-probe.py) runs 160 root and 160 private boundary
command registrations, two rich build rules, a warmup declaration and populated
manifest/ownership/analysis caches. It deliberately saves both inspection views.
The failure variant rejects from both rules. Each stage uses **three fresh normal
processes and three separate traced processes per variant**, serially with no
competing test/benchmark workloads: 24 processes total. Raw
[before](evidence/11/before-lifetimes.json) and
[after](evidence/11/after-lifetimes.json) include sample source hashes and platform.

The measurement starts after importing the library. On return it releases the
builder and, for failures, explicitly removes traceback/cause/context chains to
isolate retained error/report/view ownership. Production code does not erase those
chains. The probe retains the successful runtime or failed exception plus saved
views. After collection:

| Median | Before success | After success | Before failure | After failure |
| --- | ---: | ---: | ---: | ---: |
| Retained traced Python bytes | 3,107,326 | 405,949 | 3,250,429 | 46,837 |
| Peak traced Python bytes | 5,598,006 | 5,627,135 | 5,182,462 | 5,212,480 |
| Normal composition/build time | 99.85 ms | 100.23 ms | 87.61 ms | 87.92 ms |
| Normal peak RSS bytes | 46,268,416 | 46,186,496 | 45,891,584 | 45,957,120 |
| Active saved views | 2 | 0 | 2 | 0 |

All after samples have empty view-owned evidence/cache fields. Failed exceptions
and reports have no compiled graph. Traced retention ranges are 3,107,302–3,107,727
before versus 405,941–406,327 after success, and 3,250,366–3,250,618 versus
46,727–46,900 after failure. Runtime execution is covered separately by tests.

This demonstrates bounded retention removal for escaped views and failed-report
owners. Peak allocations rise slightly, normal timing is effectively unchanged
at this short scale, and there is **no demonstrated process-memory reduction**.
Current RSS, broad-fixture resolution timing and constructor/live-object censuses
were not measured here. Do not extrapolate these totals to the ordinary no-rule
eight-route fixture or add them to later optimization savings.

## Handoff to task 12

Construct compact selection facts directly while preserving every reader in
[11-inventory.md](11-inventory.md). Unknown build rules still require rich temporary
diagnostics. Compare no-rule run, rich-rule run and analysis separately. Preserve
candidate/target identities, declaration/boundary origins, reasons, callback order,
failed-finalization evidence and selected registration discovery; never replay a
callback to reconstruct omitted data. Keep the new graph/error ownership contract
and representative failure witnesses intact. No archived task 06–09 prototype is
production integrated, and this task makes no broader construction-saving claim.
