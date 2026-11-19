# Execution-only build and complete analyse

Investigated: 2026-10-10\
Status: Planning and source investigation only; no implementation or new benchmarks\
Authority: The maintainer requests two explicit methods, `build()` and `analyse()`,
with no validation, rules or safety-policy checks in `build()`. Breaking changes are acceptable.

## Direction

This replaces the task 10/11 contract that made structural and build-mode validation
mandatory even for production builds. That old contract is historical evidence,
not a constraint on this work. Do not introduce a hybrid mode, an `unsafe` flag,
per-check switches, rule-requirement declarations, or a compulsory analysis token.

- `build()` composes, selects and emits an executable runtime. It does not run
  registered validation rules, perform policy audits, create validation reports,
  or automatically construct inspection evidence because rules are registered.
- `analyse()` performs complete compilation analysis and all applicable built-in
  and custom validation, including today's deferred validation-only rules, before
  returning its result. Reading a completed report does not execute more rules.
- Agreed follow-up: there is one validation-rule category and registration API,
  `add_validation_rule(rule)`, with no build/validation phase argument. All rules
  belong to analyse; none belong to build. Both existing Bark UoW callbacks remain
  separate rules registered through that same API. Implementation is out of scope
  for now; this records the future contract only.
- Compilation still needs concrete instructions: target selection, dependency
  binding, generic specialization, visibility resolution, lifetime/cache placement,
  ownership and cleanup instructions are execution semantics, not optional audits.
  If no plan can be emitted, build fails at that point. It need not prove a plan
  safe, type-correct or architecturally valid before returning it.
- Selection filters, template factories, decorator conditions/positions and
  `derive()` callbacks still run where they define wiring. They are not validation
  rules. Application constructors/factories and explicit warmups are not activated
  merely by either compiler operation.
- Discovery remains runtime information. Keep `selected_registrations`, including
  implementation types and selected dependency-only/deferred/decorated paths,
  without promoting private registrations to public roots.

The proposed public shape is `make_builder().build()` for application startup and
`make_builder().analyse()` for development/CI. The return shape and builder lifecycle
of `analyse()` need the task 19 contract; a distinct analysis result owning the
report, inspectable graph and any optional test runtime is a proposal, not an API
already implemented. No separate `validation_report()` call should be required
to finish a requested analysis. No build is silently upgraded into analysis.

## Why the consumer regression changes the plan

[Actual Bark/Cop verification](/Users/peter.daly/WS/bark/bark-core/docs/evidence/clean-ioc-run-analysis-verification-20261010/README.md)
is in the local consumer repository outside this checkout.

The previous local-fix compiler hash is
`6253f5e38bd8819099db53514ede0d3c0efc4f451b3ea33f05c6e4a9932e4253`;
the current compiler hash is
`1a60386b392058ac47143b3acf4fc82b1034b95f360854dae2e98ff6cde42223`.
Both have package version `2.0.0rc4`; identify actual source bytes, not that label.

Worker measurements: native build 3.306→4.756 seconds, peak RSS 214.938→277.891 MiB,
settled RSS 213.984→274.234 MiB; three fresh untraced samples per policy. Separate
single traced samples show peak 46.566→98.799 MiB and retained allocations after GC
30.273→19.207 MiB. Linux ARM64 Docker at 500m/512 MiB/no swap shows readiness
9.461→12.866 seconds and settled anonymous memory 276.930→336.109 MiB; one container
per policy, not a distribution. Functional consumer tests pass.

Task 18's comparison started after tasks 10/11, when automatic rich capture for
build rules already existed. It measured tasks 12–17, not the cost of that policy
against the consumer's earlier compiler. Preserve its findings without treating
them as whole-upgrade acceptance. The automatic capture is a strong source-backed
lead, but its fraction of the regression is not yet isolated. A lower retained
traced heap does not demonstrate lower startup peak or settled OS memory.

## Source findings and concrete separation points

Line numbers refer to the investigated working tree and may move.

| Current path | Finding | Required separation |
| --- | --- | --- |
| `ContainerBuilder.build`, `ScopeBuilder.build` (`container.py:15857`, `15989`) | Methods translate a mode into flags and always request conservative rules | Two explicit operations with different pipelines; remove public mode selection and compatibility forwarding |
| `_build_plan` (`14617`) | Any build-mode rule enables rich diagnostics at `14657` | Rule registration has no effect on execution capture or rule invocation in build |
| `_compile_with_report` (`12758`) | Always orchestrates report/finalization and wraps even non-aggregated failures in report machinery | Shared wiring compiler, separate execution and analysis orchestration; no catch-and-ignore validation path |
| `_finalize_plan` (`11487`) | Entry-point checks, boundary descriptions, root evidence, `CompiledGraph`, unreachable checks, custom rules and `BuildReport` are bundled | Analysis owns audits/reporting; execution roots remain determined by declarations and selection |
| `_validate_captive_lifespan`, `_validate_runtime_context_dependency` (`6144`, `6179`) | Inline safety checks; the second also computes effective runtime lifespan | Remove policy checks from build, retain the computation needed for emitted steps |
| Factory specialization/registration (`7062`, `7093`, `8742`) | Return-type compatibility is computed and rejected during wiring | Analysis-only compatibility proof; retain annotation work needed for dependencies, generics and discovery |
| `_prepare_boundary_visibility` (`1803`) | Mixes shape checks and architectural checks with actual visibility/alias selection | Keep the binding operation; classify checks individually, not by helper name |
| `_compile_warmup_plans` (`12652`) | Uses a `CompiledGraph`, path traversal and `graph.manifest()` | Emit warmup targets/descriptors directly from execution roots; analysis owns warmup policy checks |
| `_observe_plan_impl` (`14217`) | Requires graph manifest/index/sharing report before instrumenting steps | Runtime instrumentation needs compact labels/identities without a full analysis graph |
| `_selected_registration_catalogue` (`10900`) | Traverses executable roots, providers, managed targets and warmup steps | Can remain independent of `CompiledGraph` and validation; preserve catalogue semantics |
| `_PlanSet`, `_reduce_explanation_metadata` (`4869`, `5177`) | Rich result fields are populated then emptied; reduction happens after analysis consumers | Prefer an execution result that never owns analysis-only fields; do not merely clear them sooner |
| `_retain_runtime_graph` (`5110`) | Retains execution-referenced Component relationships, including contextual parents and provider sources | Keep required relationships; removing validators does not eliminate selection/runtime-filter readers |
| `cli.py:_load_scope/_check`, `matrix.py:_build_variant` | Analysis mode build followed by a validation-report call | Call `analyse()` once and consume its completed result; avoid a second validation pass |

Build-only opportunities include avoiding full candidate histories, census records,
template explanation formatting, origins used only for reports, graph wrappers,
entry-point audit traversals, rule contexts, AST inspection, rich failure retries,
boundary report payloads, manifests and graph indexes. Some compact selection facts
and temporary source/component snapshots still have wiring consumers. Their removal
requires a reader audit, not an assumption that all metadata is diagnostic.

Capture also starts before compilation: registration origins, rule declarations,
builder layers and template source preparation need inspection. Moving a cost out
of the timed `build()` call does not remove it from application startup.

## Check classification to make explicit

| Kind | Proposed treatment |
| --- | --- |
| Captive lifetimes, factory-return compatibility, architecture policies, unreachable/ambiguity advisories, user validation callbacks | Analyse only, even when the existing code calls them mandatory |
| Binding dependencies, resolving provider/map targets, choosing decorators, computing cleanup owners and scope caches | Shared wiring semantics; build cannot omit them and still return the requested runtime |
| Missing required target, unresolved binding that prevents instruction emission, unsupported recursive wiring | Minimal compilation failure; no whole-graph audit or diagnostic retry needed |
| Signature-name proof, sync/async compatibility, per-call protocol conformance, warmup validity, duplicate declarations | Mixed today; task 19 must distinguish a representable-but-invalid runtime from an instruction the compiler cannot emit |
| Builder input parsing and mutation state | Keep only representation/lifecycle necessities; audit eager diagnostic checks at declaration time too |
| Runtime guards such as closed-scope handling and sync invocation of async work | Settle explicitly in task 19; no new runtime validator or fallback analysis. Execution state/cleanup must not be accidentally deleted with build-time policy checks |

Require examples that deliberately compile a representable but analytically invalid
configuration (for example a captive lifetime or definite factory-return mismatch).
`build()` should emit it without running a validator; `analyse()` should identify
the problem. Do not manufacture arbitrary missing targets or silently change the
declared wiring merely to guarantee build success.

## Contract decisions addressed by task 19

The questions below motivated task 19. Its [reviewed contract](19-contract.md)
now specifies a separate analysis result, failure/report semantics and operational
inputs. The maintainer accepted single-attempt builders and optional external
composition after review: no retry after an admitted attempt, no blueprint on
ordinary runtimes, and no separate close lifecycle for composition. Ordinary
scopes remain available without a handle. This is planning, not a memory result.

1. Does `analyse()` return a distinct result containing report/graph and an optional
   runnable test container, or a rich runtime with a completed report? How are
   partial graph failures represented, including rules that cannot run?
2. Is analysis non-consuming so `builder.analyse(); builder.build()` is allowed,
   or are separate builders required? Prefer fresh builders for the first contract;
   callback replay and retained analysis data must not contaminate production builds.
3. Where does overlay composition live? Prefer a separate composition/analysis owner;
   an execution runtime should not retain a blueprint solely for future overrides.
4. Decide minimal failure fields, warmup/profiling identifiers, and whether an explicit
   resource budget remains an operational input. None may restore implicit validation.

These questions are resolved in task 19's reviewed plan. The two-method/no-validation
direction itself does not need reconfirmation. Breaking old entry points and report
shapes is allowed.

## Work sequence

Tasks 19–25 are recorded. Task 19 design review and task 20 scoped implementation
review are complete. The maintainer has authorized tasks 21–24 sequentially:
21–24 are implemented and reviewed; 23 closes task 21's feature integration gate.
Task 24 completes the public/tooling/docs migration with full supported-Python CI
and actual Bark/Cop unit/integration verification. Source/environment baselines
and collected samples are preserved. Task 25 is now ready for assignment and
remains unassigned; it supplies real-application performance acceptance. No new
memory/startup comparison has been run.

The pre-compilation/artifact project remains separate and parked. This proposal is
about building an in-process executable runtime, not serializing a graph or loading
a pre-approved artifact. There is no new benchmark result or claimed saving yet.
