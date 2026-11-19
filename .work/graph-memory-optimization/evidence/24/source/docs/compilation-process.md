# How compilation works

Clean IoC has two public compilation operations. `build()` produces execution; `analyse()` produces completed
inspection and validation facts with an optional emitted test plan. Both consume an admitted builder attempt and
neither activates application constructors or resource factories.

## Declaration capture and binding

Builders collect registrations, providers, decorators, templates, boundaries, slots, warmups and rules. Queued discovery
uses the live class set when compilation starts. Source references are immutable declaration facts; file locations and
rich evidence are materialized only during analysis. Opaque application values retain identity.

Compilation normalizes service keys, prepares visible boundary imports and exports, specializes generic registrations,
evaluates contextual selection, expands templates and binds required dependencies. Impossible wiring fails locally.
Component relationships needed for filters, providers, ownership and cleanup are execution data and remain available
without a diagnostic graph. Missing parent singleton specializations cannot be manufactured by child overlays.

## Execution emission

The private `_ExecutionPlan` contains executable root steps, automatic declared provider roots, slots, warmup targets,
selected-registration discovery and runtime ownership data. Its registration catalogue includes selected private,
dependency-only and deferred handlers and decorators without adding public roots. Unused declaration-only roots are
not retained merely to support inspection.

The runtime owns caches and resource finalizers. Ordinary scopes share its execution plan. Root singletons remain
anchored to their declaring owner; scoped and per-resolution caches obey their compiled ownership. Runtime async,
closed-scope, provision and cleanup guards remain active. No runtime graph, report, builder or composition back-link is
required for execution.

`build()` stops here. Registering validation rules or instrumentation does not enable rich evidence, policy audits or
independent diagnostic retries. Local binding errors contain the actionable local failure rather than an analysis report.

## Analysis capture and completion

`analyse()` captures candidate decisions, source origins, explanations and graph facts while compiling. It also inspects
unused dependency-only declarations without making them executable roots. Built-in policy audits and custom rules
produce findings and coverage. Graph-dependent rules run once after a complete graph is available; missing graph,
budget and cancellation outcomes remain explicit. Invalid policy findings do not discard an otherwise emitted plan.

Independent diagnostic root attempts after failed binding retain separate attempt IDs and inconsistency evidence.
They can repeat wiring callbacks, never validation declarations, and never replace the primary executable plan.
Evidence is bounded and omitted counts remain visible. A partial graph does not pretend to be a coherent execution graph.

`AnalysisResult` owns the completed `AnalysisReport`, graph or partial graph, optional plan and retained `Composition`.
Report, manifest, census, triage and explanation reads use captured facts only. `create_runtime()` creates test runtime
state from the existing plan; it does not compile or invoke rules. Closing a result closes owned test runtimes in reverse
order and does not close a borrowed parent.

## Composition and overlays

`builder.retain_composition()` returns a pending external handle before compilation. Successful executable capture
seals immutable library declarations; opaque values remain identical. Analysis captures a handle automatically.
The handle has no close, async close or context-manager lifecycle. It retains declarations and callbacks, so callers
should keep it only when further composition is needed.

`ScopeBuilder(parent, composition=handle)` verifies matching live parent lineage and restores declarations owned by the
child builder. A new overlay compilation can rerun template factories. Reads of the handle, result or runtime do not.
Ordinary `parent.new_scope()` needs no handle and never recompiles.

## Observation and tooling

Resolution profiling observes the execution plan directly. Execution IDs identify observation installations, with
ordinary scopes aggregating under their installation. Cache groups describe actual registration key, owner binding and
lifespan families; they are not a census of live cache entries. Paths use occurrence identities plus display labels.
Warmup reports use `plan_id`, and SARIF uses `executionPlanId`; neither requires a graph manifest fingerprint.

CLI check, explain, manifest, diff, census and triage use completed analysis. Compilation profiling explicitly selects
`build` or `analyse`. No private historical compiler harness is a supported third operation. Experimental artifact
serialization remains parked and unsupported; it is not a public precompilation or deployment feature.

For public usage see [build and analysis](validation.md), [compiler tooling](compiler-tooling.md),
[composition scopes](scopes.md), [custom validation](custom-validation.md) and [compilation budgets](compilation-budgets.md).
