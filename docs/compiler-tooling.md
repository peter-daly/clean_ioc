---
description: Inspect, validate, render, and diff Clean IoC's compiled dependency graph in Python or CI.
---

# Compiler tooling

Clean IoC exposes the compiled dependency graph as a build artifact. Mark application entry points to focus the default
tooling view, then inspect the component plans used by runtime resolution.

```python
from clean_ioc import ContainerBuilder

builder = ContainerBuilder()
builder.register(PaymentGateway, StripeGateway)
builder.register(Checkout, root_policy="entrypoint")

container = builder.build()
print(container.build_report.to_text())
print(container.graph.to_text())
```

`root_policy` classifies each registration:

| Policy | Build and resolution behavior |
| --- | --- |
| `"entrypoint"` | Public root, also marked for the focused graph view. |
| `"resolvable"` (default) | Public root without a tooling marker; this is the existing registration behavior. |
| `"dependency_only"` | Available to dependencies, but not directly resolvable as a root. An unused registration is discarded by default. |

`build(clean_orphans=False)` retains and validates otherwise unused dependency-only registrations as graph roots for inspection. They remain unavailable to direct resolution. With the default `clean_orphans=True`, unused dependency-only registrations and their unneeded graphs are omitted from the frozen container. A broken dependency inside an omitted orphan does not fail the build.

`mark_entrypoint()` remains available for request-level markers, such as a filtered selection or `list[MessageHandler]`. An entry-point marker focuses tooling; it does not change a registration's root policy. Once any entry point is marked, registrations outside all marked component trees produce `unreachable-component` warnings.

Mark a collection when every implementation is an application entry point:

```python
builder.mark_entrypoint(list[MessageHandler])
```

## Failure aggregation

Both `ContainerBuilder.build()` and `ScopeBuilder.build()` accept `aggregate_errors: bool = True`.
The compatibility default independently recompiles roots after a reportless compilation failure to collect
additional findings, with or without optional `diagnostics` capture. CLI `check` and matrix validation keep this
aggregate behavior. An application production root can pass `aggregate_errors=False` to skip those diagnostic
root retries:

```python
container = builder.build(
    aggregate_errors=False,
    diagnostics=False,
    provider_roots=(),
    allow_scope_builders=False,
    check_unreachable=False,
)
```

Every essential structural check remains enabled. Missing dependencies, cycles, lifespan/ownership errors,
provider admission, boundary contracts, entrypoint/warmup validation and build-mode application rules still fail
the build. The flag controls recompilation for diagnostics; it does not turn every compiler phase into immediate
first-error processing. Already collected preparation findings and report-bearing validation/build-rule failures
keep their existing full reports. A failed builder remains reusable.

For a reportless compiler failure, no-retry mode preserves the original error code, complete path and captured
structural evidence in `ContainerBuildError.report`, including the defining boundary. Arbitrary callback exceptions
keep a safe redacted message and the request path captured at selection/eligibility failure, without inspecting
user exception text or invoking the callback again. Unsupported arbitrary failures can remain without a path or
structured evidence. With `diagnostics=True`, the partial graph contains only the primary attempt and its usual
bounded witness; `diagnostics=False` retains no optional partial graph. `report.checked_roots` and partial-graph
root counts are zero for diagnostic roots in this mode, not a claim that primary compilation did no work.
No diagnostic-attempt budget is consumed; all primary callback and compilation allowances remain enforced.
A profiling failure still finishes with state `failed` and records no diagnostic root retry phase.

The flag is independent of `diagnostics` and is not stored in the successful runtime. Successful executable graphs,
selected registration catalogues, validation reports, activation, ownership and cleanup are identical. Ordinary
scopes never compile. Each overlay build chooses its own aggregation setting, defaulting to compatibility behavior.

## Declared provider roots

`build(provider_roots=None)` is the compatibility default: every resolvable ordinary service gets `Provider`,
`AsyncProvider`, `ManagedProvider` and `AsyncManagedProvider` roots for the scalar target and its `list`,
`tuple[T, ...]` and `set` forms. Both container and overlay builders accept `provider_roots`.

Applications that only inject deferred handles can call `builder.build(provider_roots=())`. To expose specific
handles through public `resolve()` calls, supply their complete annotations:

```python
from clean_ioc import AsyncProvider, ContainerBuilder, Provider

builder = ContainerBuilder()
builder.register(PaymentGateway, StripeGateway)
container = builder.build(provider_roots=(AsyncProvider[PaymentGateway], Provider[list[PaymentGateway]]))
```

The iterable declares public resolution capabilities independently of `diagnostics`. Omitted automatic provider
forms are unavailable to `resolve()` and `has_component()`. Ordinary roots, root filters and ordinary collections
remain available. Injected providers and provider maps still compile their dependency-specific targets normally.
Marked provider entrypoints are included automatically. Duplicate annotations and type aliases are normalized.
Invalid annotations or missing declared targets fail before activation; a failed build leaves the builder reusable.

A managed acquisition can use `ResolutionContext` to select any already-compiled ordinary root. The compiler
therefore retains a private frozen `AsyncManagedProvider` scalar closure when managed handles are injected or
requested, and the corresponding collection adapters when public deferred collection handles require them.
This closure is unavailable to public resolution unless declared. Its physical records/views and adapter work
count normally against compilation budgets and profilers. Full mode shares its public managed plans with the
private closure. The compiler omits the closure when absence of managed acquisition is proven; boundaries and
inherited singleton/pre-configuration plans conservatively retain it. Runtime resolution never extends the graph,
compiles dependencies or reruns build-time selection/validation callbacks.

An overlay's own `provider_roots` argument controls its public provider forms; omitted/`None` restores the full
compatibility mode. Existing escaped handles and inherited singleton ownership keep their original compiled
activation plans. Default collections of unmarked provider handles retain their existing empty semantics.

## Selected runtime registration discovery

`container.selected_registrations` and `scope.selected_registrations` expose a frozen tuple of `RegistrationInfo`
records for registrations reachable through the scope's retained executable roots, public provider forms,
private managed targets and warmup plans. Reading the tuple does not resolve services, compile dependency trees,
or rerun selection callbacks. Ordinary nested scopes reuse the same tuple; a compiled overlay receives its own
catalogue, including the selected dependencies of inherited anchored singletons.

Each entry supplies `id`, canonical visible `service_type`, static `implementation_type`, `name` and immutable
`tags`. Explicitly closed constructor aliases and typed factory result aliases remain closed. Unknown factory
result types are `None`; static discovery never makes result reflection a new activation requirement. The
catalogue contains selected registration and decorator definitions, including dependency-only registrations
reached through provider maps and deferred handles. Synthetic provider/collection/context/value nodes, dead
dependency-only definitions, rejected candidates and unexposed architecture-only boundary roots are excluded.
Boundary aliases appear with the service type visible in their executable plan. Dependency metadata follows
the actual selected target, including targets inside an exposed boundary plan.

Entries are deduplicated by registration ID and visible canonical service type, in deterministic depth-first
root/dependency traversal order. Multiple closed requests or visible service aliases of one registration may
produce multiple entries. The tuple retains metadata and type references, without `Component`, graph or builder
blueprint references, and remains available with `diagnostics=False`.

Use this catalogue for static type discovery that does not need public component resolution. `scope.components`
continues to expose public root occurrences; applications that resolve returned component IDs should keep using it.

## Optional diagnostic capture

`ContainerBuilder.build()` and `ScopeBuilder.build()` use `diagnostics=False` by default. Ordinary builds still compile
all visible roots, check missing dependencies, cycles, retaining lifespans, ownership, aliases and decorator safety,
and run build validation rules. With the default `explain_metadata=True`, runtime resolution, component discovery, graph traversal, manifests, ownership
reports, source-linked findings and compilation/runtime profilers remain available.

Use `builder.build(diagnostics=True)` for recorded candidate history, occurrence explanation paths, argument and
specialization explanations, failed-build partial graphs and selection census. The flag must be a boolean. Rich
history is captured during compilation; it cannot be added to an existing scope without rebuilding. For anchored
parent singleton explanations in an overlay, build the parent with diagnostics enabled too: an overlay cannot
recover omitted parent parameter/predicate history.

`scope.graph.diagnostics_enabled` and `error.diagnostics_enabled` report the requested mode. With capture disabled,
`graph.explain(component).selected` still exposes the actual compiled component identity, fallback status and declaring
origin/layer. It labels ordinary presence as `compiled-occurrence`, without inventing predicate evaluations.
Optional selected-decision policy fields (`preferences`, `parent_precedence`, `template`), its `path`, `rejected` and full serialization raise `ValueError` explaining that `diagnostics=True` is required.
`explain_decorators(component)` retains the captured selected/rejected decorator and template facts needed by safety
rules, with the same explicit restriction on explanation paths/serialization. `explain_template_sources()` retains
source-filter facts without replaying callbacks. Semantic graph paths remain available through `graph.walk()`.

Rich-only APIs raise `ValueError` with an opt-in instruction instead of presenting empty evidence as complete.
Default failed builds still aggregate independent root failures and preserve concise error paths, source evidence and
budget findings; `error.partial_graph` is `None`. Independent-root recovery continues to count against compilation
budgets in either mode.

CLI validation/inspection commands enable diagnostics when they build a supplied builder/factory;
`clean-ioc profile` uses the normal build default and enables capture only with `--diagnostics`.
`BuildMatrix.check()` enables diagnostics for
variant builds before running validation. Calling `validation_report()` on an existing scope runs its validation
rules against the existing graph; it does not recompile or enable previously omitted history. Supply an unbuilt
builder to the CLI or build a scope with `diagnostics=True` when a validation rule needs rich evidence.

## Optional explanation metadata

Both build entry points accept `explain_metadata=True` by default. Set it to
`False` to release successful-build explanation indexes, origins, candidates,
inspection caches and records outside the required runtime relationships.

```python
from clean_ioc import ContainerBuilder

class Service:
    pass

builder = ContainerBuilder()
builder.register(Service)
with builder.build(explain_metadata=False, allow_scope_builders=False) as container:
    assert isinstance(container.resolve(Service), Service)
    assert not container.explain_metadata_enabled
    with container.new_scope() as scope:
        assert isinstance(scope.resolve(Service), Service)
```

The runtime keeps resolvable root Components and every relationship required by
runtime filters, providers, maps, resolution contexts, ownership and cleanup.
`components`, `has_component`, filtered resolution, ordinary scopes, provisions,
warmups and instrumentation still work. Components retain generic bindings,
build arguments, names, tags, aliases and ownership facts needed by filters.
No inspection callback is replayed and no inspection cache reconstructs discarded
facts after resolution.

`graph`, its traversal/explanation/manifest/census/architecture APIs,
`selected_registrations` and `validation_report()` raise `RuntimeError` containing
`explain-metadata-disabled`. The scalar `build_report` remains available, including
its checked-root count and captured issues; its SARIF output has no retained graph
context. Build validation and build-mode rules always run before metadata is
released. Validation-only rules are incompatible with this option and cause a
clear `ValueError` before compilation. With `check_unreachable=False`, unreachable
warnings stay unchecked and cannot be requested later through `validation_report()`.
Use `check_unreachable=True` when those warnings are needed in the stored report.

| diagnostics | explain_metadata | Successful runtime | Failed build |
| --- | --- | --- | --- |
| False | True | Existing inspection and safety facts | Existing minimal failure evidence |
| True | True | Existing full diagnostic inspection | Full requested diagnostic evidence |
| False | False | Runtime relationships and scalar build report | Existing minimal failure evidence |
| True | False | Runtime relationships and scalar build report | Full requested diagnostic evidence |

Diagnostics control failure/build capture independently of successful runtime
retention. Temporary compilation facts needed for validation and failure evidence
may still be captured, then released after success. Warmup planning and optional
instrumentation capture their small runtime descriptors before graph inspection
is disabled. Resolution profiling remains usable; graph-dependent analyses of a
profile require an independently retained full graph.

`allow_scope_builders` remains independent. Keeping it enabled retains declaration
layers and private architecture anchors for future overlays, while completed
source-inspection graphs and template expansion evidence are released. A reduced
parent requires `scope_builder.build(explain_metadata=False)`; requesting full
metadata from that parent raises `ValueError`, because inherited facts cannot be
recovered. A full parent can create either kind of overlay. Ordinary descendants
inherit their existing plan's metadata mode. Reducing a child never changes an
ancestor's graph or releases memory still owned by that ancestor.

Build callbacks receive valid Components while running. After a successful reduced
build, Components from discarded compilation paths raise `RuntimeError` containing
`explain-metadata-disabled` when their metadata is accessed; their occurrence IDs
remain available for logging. Saved Components in the retained runtime closure
remain usable, including all their relationships. Separate source-inspection
snapshots remain caller-owned and usable; retaining them keeps their own graphs
alive. Saved inspection graphs supplied to build validation rules explicitly
expire and release their context. These limits apply only to the explicit reduced
mode; full builds keep existing escaped-view behaviour.

Retaining a builder, a callback closure, a source snapshot or a full ancestor can
keep application-owned data alive. Release those owners when their work is done.
The private schema-7 artifact experiment supports the reduced local fixture;
it remains an unfinished experiment with no public persistence API.
Build matrices continue to use full metadata because their contract includes
manifests and graph comparisons; this option does not add a reduced matrix mode.

## Deferred reachability advisories

Both builder types accept `check_unreachable=True` by default, preserving the existing
`unreachable-component` warnings in `build_report`. Production composition can pass
`check_unreachable=False` to defer this scan to `scope.validation_report()` or the CLI
`check` command. The flag must be a boolean and is independent of diagnostic capture
and provider-root selection. It affects only unreachable-component warnings; missing
entrypoints, boundary contracts, dependency/lifespan errors, other built-in findings,
build-mode application rules and compilation callback budgets always remain active.

A deferred runtime's `build_report` omits these warnings. `validation_report()` returns
them alongside stored build findings and fresh validation-only rule results, without
altering the stored report. Reachability is recovered from immutable graph roots and
selected entrypoints, including dependencies, pre-configurations and decorators; it
never reruns selectors, constructors, factories or template preparation. This works
for ordinary descendants, compiled overlays and compact runtimes built with
`allow_scope_builders=False`, without retaining composition to support the scan.
Strict CLI checks therefore still fail for deferred unreachable warnings unless the
warning code is explicitly ignored. A failed build with deferred checking reports its
essential findings immediately; it has no runtime on which to request advisories.

With `diagnostics=False`, entrypoint selection evaluates the same eligible candidates
and callbacks in the same order, including fallback suppression and provider target
filters, but retains no selected/rejected entrypoint histories or census records.
`graph.explain(component)` still provides minimal compiled origin/layer/fallback facts;
service/filter explanations and selection census require `diagnostics=True`.
Graph manifests and boundary contracts keep their existing shape.

## Structured build reports

A successful runtime exposes its immutable `BuildReport` as `container.build_report`. A failed build raises `ContainerBuildError` with the same report on `error.report`.

## Inspect a failed build

With `diagnostics=True`, failed builds also expose `error.partial_graph`: a frozen, non-executable diagnostic snapshot. It records only
structural labels, completed draft branches, observed failing parameter edges, and known selection candidates.
Evaluated candidates are marked `complete`, `failed`, or `rejected`; known candidates compilation did not visit are
marked `not-examined`, never rejected. Cycles use explicit back-reference edges and attempts
retain their safe witness paths. It deliberately does not freeze a
runtime graph, execute constructors or callbacks, or serialize configured values or exception text.

```python
from clean_ioc import ContainerBuildError

try:
    builder.build(diagnostics=True)
except ContainerBuildError as error:
    print(error.partial_graph.to_text())
```

Independent error-report retries remain separate attempts in this artifact; they are not merged into a graph that
looks coherent. Capture is bounded (500 nodes and edges per attempt), and reports truncation explicitly. JSON includes
graph-level `total_attempts`, `retained_attempts`, `omitted_attempts`, `total_roots`, `retained_roots`, and
`omitted_roots`; each attempt includes `witness_total` and `witness_omitted` when its witness path is clipped. Use the CLI
to write an artifact while retaining a failing exit status:

```console
clean-ioc graph my_app.composition:application_builder --on-error partial --format json -o failed-graph.json
```

```python
from clean_ioc import ContainerBuildError

try:
    container = builder.build()
except ContainerBuildError as error:
    for issue in error.report.errors:
        print(issue.code, issue.path, issue.message)
```

Independent root failures are aggregated so one build can report several composition mistakes. Issues have a stable code, `error` or `warning` severity, a message, and a semantic component path. Errors always fail the build; warnings are available for policy in tooling and CI.
With `diagnostics=True`, when compilation reached candidate selection before failing, `ContainerBuildError.explanations` contains the safe partial
decision records captured up to that point; retrying the repaired builder creates a fresh index.

### Triage repeated failures

`ContainerBuildError.triage_report()` summarizes supported structural failures using facts captured at the failure
site. Its `BuildTriage` groups include the original `issue:1`, `issue:2`, etc. references, distinct affected roots,
marked entry points when known, separate `attempt:1`, `attempt:2`, etc. references, bounded witness paths, and a fixed
investigation hint. The original `BuildReport` and its JSON format are unchanged.

```python
from clean_ioc import ContainerBuildError

try:
    builder.build()
except ContainerBuildError as error:
    triage = error.triage_report()
    print(triage.to_text())
    saved_json = triage.to_json()
```

```console
clean-ioc check my_app.composition:application_builder --triage --format json
```

For example, `PlaceOrder` and `CancelOrder` can both fail because their dependency paths request the same missing
`Clock` in the `orders` boundary. Triage reports one group with two member findings and two separate retry attempts.
A missing `Clock` at the root, a named `Clock` request, or an `orders` request rejected by a filter stays separate
unless its captured selection context proves equivalence. Captive dependencies retain the actual retaining ancestor;
cycles retain their directed registration sequence; generic failures retain the requested specialization and template.
Arbitrary custom findings, callback failures, and early errors without this evidence remain individual findings.

The `BuildTriage.from_report(report, evidence=...)` factory also accepts validation-only reports. Without captured
compiler evidence, each finding remains ungrouped. `to_text(detailed=True)` shows every member and attempt reference;
`to_json()` always includes the full original findings. `evidence_incomplete`, `inconsistent_retries`, and attempt
counts mark uncertainty and truncated capture. Group counts describe recorded evidence. Fixing one group may expose
further failures in the next build; a group is an investigation lead, not a repair guarantee. Rendering a captured
triage report does not invoke application constructors, derivations, filters, or validation rules.
For manually supplied entry-point context, pass `(boundary_name, root_label)` pairs; use `None` for the root area.
Failed-build triage also retains each finding's compilation boundary even when a callback error has no grouping
evidence. A standalone `BuildTriage.from_report(report)` cannot recover that area, so its affected-root count is
labelled a lower bound when issue locations are unknown.
JSON count-status fields label exact issue/attempt totals, retained detail counts, lower-bound witness counts when
partial capture was truncated, and unknown entry-point membership when no declaration context was supplied.

Current issue codes include:

- `missing-component`, `missing-entrypoint`, and `ambiguous-selection`;
- `factory-return-type-mismatch` for a definite incompatibility between a factory annotation and its registered service;
- `circular-dependency` and `captive-dependency`;
- `generic-specialization` and `overlay-singleton`;
- `invalid-argument` and `invalid-derived-argument`;
- `validation-rule-error` for a broken custom validation callback;
- `unreachable-component`.

Applications may add their own stable codes by registering a custom graph rule. Each rule receives a per-pass
`ValidationContext` containing the graph and lazy type-AST inspection. Custom issues use the same report, JSON, CLI
strictness, and warning-suppression behavior as compiler findings. Rules use `mode="build"` by default. Set
`mode="validation"` to skip a rule during application builds and run it only during explicit validation. Build rules are not
rerun during that validation; their stored findings remain in the aggregate report. Use
`context.graph.walk()` for a deterministic all-roots traversal; each returned `GraphVisit` retains the component objects
and the matching diagnostic path. See [Custom graph validation](custom-validation.md) for the complete rule cookbook.

## Render the compiled graph

The graph includes registrations and activation edges for decorators, pre-configurations, default and configured values,
runtime contexts, and declared scope slots. Decorator pipelines render outside-to-inside with their
positions and metadata. Nodes describe components; edges consistently describe their relationship as
`depends on: <argument>`, `decorated by`, or `pre-configured by`.

```python
text = container.graph.to_text()
mermaid = container.graph.to_mermaid()
manifest = container.graph.manifest()
ownership = container.graph.ownership_report()

print(manifest.fingerprint)
print(ownership.to_text())
```

Renderers and manifests show marked entry points by default. Pass `all_roots=True` to inspect every compiled root.
`graph.walk()` is intentionally different: validation traversal always includes every root so an entry-point marker
cannot weaken a policy rule.

The compiler reuses diagnostic type names within each compilation, including nested generic names and equal immutable
label strings. Type and callable metadata is a first-use snapshot for that compiler: changing a name in a build callback
does not change already-rendered labels. Independent builds, diagnostic retries, and overlay compilations use fresh
caches, and the public `qualified_name` helper continues to read current metadata on every call. Frozen plans retain
only the resulting strings; compiler caches and their source references are released with the compiler. This reuse
never invokes user hashing, equality, or object representations and does not cache activation or selection results.

The JSON manifest is deterministic across equivalent builds. It uses semantic paths and qualified type names instead of component UUIDs or memory addresses. Fixed values are represented by type and activation kind; their contents are not serialized. Build-argument keys and values are also omitted from manifests, fingerprints, build reports, ownership reports, text output, and Mermaid output. Wiring changes selected by those inputs remain visible in the compiled graph. This makes manifests suitable for review without leaking configured secrets.

```python
from clean_ioc import GraphManifest

baseline = GraphManifest.from_json(saved_json)
difference = container.graph.manifest().diff(baseline)

for change in difference.changed:
    print(change.path)
```

Manifests include `cache_owner`, `cleanup_owner`, and a semantic `owner_path` on every node. A diff reports added,
removed, and semantically changed component paths and boundary contracts.

Use `container.graph.diff(baseline)` for classified changes with known current entry points, and
`difference.evaluate(DiffPolicy(...))` to enforce risk thresholds, denied kinds, and path allowances.
See [Graph-change policies](graph-change-policies.md) for complete Python and CLI examples.

[Build-variant matrices](build-matrices.md) compile an explicit set of supported configurations, aggregate each
variant's build and validation findings, and apply entry-point and semantic-drift policies against a named reference.
Use `clean-ioc matrix module:object --format json` or `--format sarif` for combined reports.

Graph manifests, build reports, and ownership reports are unversioned in this release candidate. They omit schema
version fields, and readers use the current format without version checks or migration adapters. Regenerate saved graphs
and baselines when the format changes. Schema versioning is planned for a future release. Deterministic ordering and
redaction still apply.

`OwnershipReport` is a frozen, activation-free proof over the compiled graph. Each record includes the component's
semantic path, cache and cleanup categories, the cached ancestor responsible for promotion when applicable, and a
value-free reason. Runtime owner tokens, cache keys, scope IDs, finalizer callables, configured values, and build inputs
never appear in the report.

## Analyze graph impact, sharing, and activation

Compiled graph analysis reuses the same semantic paths as manifests and does not activate application code. It keeps
three ideas separate:

- reverse dependency impact: which compiled roots and entry points can reach a target;
- static sharing eligibility: which occurrences can use the same cache group under a runtime scenario;
- activation obligations: what resolving a root can require immediately and what is deferred behind providers.

```python
impact = container.graph.dependents(PaymentGateway, match="registration")
print(impact.to_text())

sharing = container.graph.sharing_report(Database)
print(sharing.to_json())

activation = container.graph.activation_report(Checkout, scenario="cold")
print(activation.to_text())
```

Use `match="occurrence"` with a component from `component_at_path(...)` when a repeated registration must be inspected
at one exact graph position. Registration matching includes every occurrence of that exact registration. Deferred typed
provider targets are excluded from impact summaries unless `include_deferred=True`.

`SharingReport` describes static cache eligibility, not a live heap. Transient entries are reported as uncached
activations. Per-resolution, scoped, singleton, and supplied groups state their assumptions without exporting raw
registration IDs, cache keys, owner tokens, runtime scope IDs, configured values, or object representations.

`ActivationReport` supports `cold`, `warm_singletons`, and `warm_scope` scenarios. These are hypothetical assumptions:
the report does not inspect actual caches or provided scope values. Immediate obligations stop at provider handles;
provider targets are listed as deferred obligations. A warm cache scenario may skip construction work in the summary,
but public sync/async resolution constraints still come from the compiled root.

The report also separates async causes, potential constructions, and cleanup owners. Execution relationships describe
pre-configurations as before-core work, decorators as after-core work, provider targets as on-demand work, and async
collection members as potentially concurrent rather than inventing a total execution order. Runtime-context resolution
remains explicitly unknown because application code may issue declared or unrestricted requests.

## Explain compiler decisions

`CompiledGraph.explain(...)` reports why a root or exact occurrence was selected and which candidates were rejected.
The result is an immutable `CompilationExplanation` with stable reason codes, declaration origins, and text/JSON
renderers:

```python
import clean_ioc.component_filters as cf

default = container.graph.explain(PaymentGateway)
stripe = container.graph.explain(
    PaymentGateway,
    filter=cf.with_name("stripe"),
)

gateway = next(
    dependency
    for dependency in checkout_component.dependencies
    if dependency.service_type is PaymentGateway
)
dependency_choice = container.graph.explain(gateway)
```

Origins identify the registration, decorator, pre-configuration, scope-slot, entry-point, validation-rule, or synthetic
definition, its root/overlay layer, its logical bundle path, and a best-effort source location. Paths in explanation JSON
are relative to the build working directory when available. Source inspection is best-effort and never makes a build
fail.

Explanations read decisions captured during compilation. They do not invoke filters or user activation code. Default
and exact-name root requests can always be explained; an arbitrary root filter can be explained when that same filter
was evaluated for a marked entry point during compilation. Collection explanations include every matching member.
Configured values, build arguments, filter closure state, callable representations, memory addresses, and runtime IDs
are never included. Provenance is deliberately absent from graph manifests, so it does not affect fingerprints.

### Explain decorator templates

For a successful build, `graph.explain_template_sources(template_id)` returns the captured selection for each visible source registration considered by that template. Each `TemplateSourceDecision` has a `source_registration_id`, `selected`, source service/implementation labels, generic source bindings, and `generated_definition_id` when selected. Omitting `template_id` returns decisions for all templates.

Pass a target `Component` to `graph.explain_decorators(component)` to inspect selected and rejected decorators for **that occurrence**. A selected template decision includes the template ID, source registration ID, target registration ID, and target occurrence ID. Registration IDs identify declarations; occurrence IDs distinguish the same declaration under different parent contexts. `graph.explain(component)` explains candidate selection for the component itself. For a generated wrapper, pass its decorator component to `graph.explain(wrapper)` to see its template declaration origin; the core component retains its ordinary registration origin. See [decorator templates](decorator-templates.md#inspection-and-errors).

These explanations are frozen, value-free decisions; reading them does not rerun `source_filter`, `when`, or the factory. They require a successfully built graph. If a source filter or factory fails before graph construction, inspect `ContainerBuildError.report` for its template/source path and `error.partial_graph` for the bounded attempt/witness instead. Such an early failure cannot provide a completed target-decision list.

### Explain parameter policies and generic substitutions

For an exact occurrence, `explain_arguments()` reports the policy that was compiled for every parameter. It records the
declared and canonical annotation, whether Python supplied a default, the result category, and selected semantic graph
paths;
fixed and derived values are reported only as redacted values. Inspection reads frozen data and does not call `derive`,
filters, constructors, or factories again.

```python
component = container.graph.component_at_path(
    "root:my_app.Checkout:default:0/dependency:serializer:0"
)
for parameter in container.graph.explain_arguments(component):
    print(parameter.parameter, parameter.policy_kind, parameter.result_category)

specialization = container.graph.explain_specialization(component)
print(specialization.service_bindings)
print(specialization.factory_pattern_bindings)  # a distinct TypeVar scope
```

`build_arg(...)` is identified as an explicit build input but its key and value are never exposed. `generic_arg(...)`,
`derive(...)`, `inject()`, `select()`, fixed arguments, Python defaults, and implicit injection remain distinct policy
kinds. Generic records preserve before/after dependency annotations and keep service and structural factory-pattern
bindings separate. They are compiler evidence, not a new runtime type check. `ParameterExplanation.to_dict()` omits
provenance by default so equivalent builds serialize identically; pass `include_provenance=True` when source metadata is
needed for an interactive or local report.
Only successful specializations have a graph occurrence and therefore a `GenericBindingExplanation`; an unsuccessful
build exposes its existing redacted selection/failure explanations instead of reconstructing bindings by re-running
user code.

## Reverse dependencies and impact

`graph.dependents(...)` builds a lazy, immutable sidecar index from the compiled plan. It does not run constructors,
factories, filters, or argument policies, and it leaves manifests and their fingerprints unchanged. Select a concrete
occurrence when its path matters, or select one registration to include every compiled occurrence of that registration:

```python
impact = container.graph.dependents(PaymentGateway, match="registration")
for root in impact.affected_entrypoints:
    print(root.path, impact.witness_paths[root.path])

# Provider targets are a separate deferred edge category.
including_deferred = container.graph.dependents(
    PaymentGateway,
    match="registration",
    include_deferred=True,
)
```

Type selectors reject ambiguity; pass `name=` for a named registration or use `graph.component_at_path(...)` for an
exact occurrence. `GraphReference` serializes its semantic path and display metadata, never registration UUIDs or
runtime identities. `graph.paths_between(root, dependency, max_paths=100)` returns a bounded `GraphSlice`; its
`truncated`, `returned_paths`, and `max_paths` fields make an incomplete path list explicit. Use
`graph.shared_dependencies(first_root, second_root)` to find registrations reachable from both roots without treating
repeated occurrences as separate registrations.

## Count recorded registration selections

`graph.selection_census()` inventories declarations and counts selections in the marked entry-point view. When no entry
points are marked, it uses all public compiled roots. `graph.selection_census(all_roots=True)` uses every public
compiled root, including named roots. Public and boundary-local roots have separate `analyzed_roots` labels and each
root example carries its composition area. `include_deferred=False` omits provider and per-call targets. The inventory
still includes definitions with no recorded request in the selected view. Definitions inside a boundary remain private unless
exposed through that boundary; an alias links back to its source declaration and does not imply another instance.

```python
from clean_ioc import ContainerBuilder


class Gateway:
    pass


class DefaultGateway(Gateway):
    pass


class NamedGateway(Gateway):
    pass


class Checkout:
    def __init__(self, gateway: Gateway, gateways: list[Gateway]):
        pass


builder = ContainerBuilder()
builder.register(Gateway, DefaultGateway)
builder.register(Gateway, NamedGateway, name="named")
builder.register(Checkout)
builder.mark_entrypoint(Checkout)
report = builder.build(diagnostics=True).graph.selection_census()
print(report.to_text())
print(report.to_json())
```

Here the default is selected by one single-service dependency and included by one collection request. The named-only
registration is rejected by the default-name filter in those two requests. An `all_roots=True` report separately counts
root lookups for both registrations; it does not turn a root lookup into a dependency use. A marked collection root has
its own `root_collection_inclusions` count. Deferred provider and per-call targets have their own use count and phase.
Generated decorators link to both their source registration and template;
template source-filter outcomes are declaration-wide composition evidence, independent of the root view. An open
generic or structural pattern appears as one declaration even without a closed request. Closed selections report
specializations under that source declaration; an unrequested pattern says “No recorded request.”

Each summary has exact counts for the recorded successful view and at most eight example outcomes; `omitted_examples`
states how many more examples were captured. `recorded_requests` counts observed decisions, not hypothetical requests.
The compiler never reruns a predicate, derivation, key function, or template callback for this report. A failed build
offers `error.selection_census()` with `complete=False`: selected, rejected, failed, and not-examined evidence from its
primary attempt are shown in separate attempt counts, and selection totals are lower bounds. A missing selection
record is unknown, not proof of rejection.

The census answers where declarations participated in recorded compiler requests. Entry-point reachability warnings
answer whether compiled nodes are reachable from marked roots. Runtime observation coverage answers what actually
activated during observed executions. None of these reports proves that a registration is unused by the application
or safe to remove. The census is informational and does not alter graph manifests or fingerprints.

## Use it from the command line

Expose a builder, built scope, or zero-argument composition factory from an importable module:

```python
# my_app/composition.py
def application_builder():
    builder = ContainerBuilder()
    builder.register(PaymentGateway, StripeGateway)
    builder.register(Checkout)
    builder.mark_entrypoint(Checkout)
    return builder


def application_container():
    return application_builder().build()
```

The target may be a builder, a built container or scope, or a zero-argument factory function returning any of them.
The CLI calls a factory exactly once. A factory that returns a builder is then built; a factory that returns a container
is inspected directly.

Validate, render, and diff it without starting the application:

```bash
clean-ioc check my_app.composition:application_builder
clean-ioc check my_app.composition:application_container
clean-ioc check my_app.composition:application_builder --format sarif -o clean-ioc.sarif
clean-ioc graph my_app.composition:application_builder --format mermaid
clean-ioc graph my_app.composition:application_builder --format json -o dependency-graph.json
clean-ioc ownership my_app.composition:application_builder --format json
clean-ioc census my_app.composition:application_builder --format json
clean-ioc census my_app.composition:application_builder --all --exclude-deferred
clean-ioc diff my_app.composition:application_builder dependency-graph.json
clean-ioc impact my_app.composition:application_builder my_app.ports:PaymentGateway
clean-ioc impact my_app.composition:application_builder --path 'root:my_app.Checkout:default:0/dependency:gateway:0'
clean-ioc sharing my_app.composition:application_builder my_app.infra:Database --format json
clean-ioc activation my_app.composition:application_builder my_app.use_cases:Checkout --scenario warm_singletons
clean-ioc explain my_app.composition:application_builder my_app.ports:PaymentGateway
clean-ioc explain my_app.composition:application_builder my_app.ports:PaymentGateway --name stripe --format json
clean-ioc explain my_app.composition:application_builder --path 'root:my_app.Checkout:default:0/dependency:gateway:0'
clean-ioc explain my_app.composition:application_builder --path 'root:my_app.Checkout:default:0' --arguments
clean-ioc explain my_app.composition:application_builder --path 'root:my_app.Checkout:default:0' --arguments --argument timeout --format json
clean-ioc explain my_app.composition:application_builder --path 'root:my_app.Checkout:default:0/dependency:serializer:0' --specialization
clean-ioc impact my_app.composition:application_builder my_app.ports:PaymentGateway --match registration
clean-ioc impact my_app.composition:application_builder --path 'root:my_app.Checkout:default:0/dependency:gateway:0'
```

`check` always runs the complete validation rule set and is strict by default: it exits non-zero for errors or
unsuppressed warnings. `--ignore CODE` suppresses a warning code from either kind of rule; errors cannot be ignored.
Pass `--no-strict` to leave warnings informational without skipping rules. The explicit `--strict` form is also accepted
when a CI command should state the warning policy directly.

`check --format sarif` exports source-linked findings and dependency code flows for CI viewers.
Text, JSON, and SARIF support `-o` for successful and failed checks. See
[Source-linked CI reporting](sarif.md) for GitHub upload configuration and programmatic exports.

`diff` exits `0` when the graph is unchanged and `1` when it changed. Add `--all` to `graph` or `diff` when the baseline should include every root rather than the entry-point view. Baselines are never updated implicitly.
`ownership` emits the frozen all-roots ownership proof as text or JSON and does not activate components.
`census` emits text or JSON and exits `0` even with zero selections. If the build fails, it emits the partial census and
exits `1`; invalid input or output exits `2`.
`impact`, `sharing`, and `activation` emit text, JSON, or Mermaid and exit `2` for invalid targets, paths, or ambiguous
selectors. Impact analysis is informational; high fan-in does not fail a build.
`explain` exits `0` for an explanation, `1` when the target does not build, and `2` for an invalid target, service,
manifest path, or ambiguous selection. `--path` and the service locator are mutually exclusive; the initial CLI supports
default and exact-name root selection.
`impact` is informational and exits `0` even when no consumers are found; invalid paths, missing services, and
ambiguous type selections exit `2`. Use `--include-deferred` to cross provider-target edges.

Example CI policy:

```yaml
- name: Validate dependency graph
  run: clean-ioc check my_app.composition:application_builder
- name: Detect dependency graph changes
  run: clean-ioc diff my_app.composition:application_builder dependency-graph.json
```

Update the checked-in manifest only after reviewing the corresponding composition change.

## Profile one compilation

Profiling uses the same `diagnostics=False` default as an ordinary build. To measure a build that captures optional
diagnostics, pass `diagnostics=True` in Python or `--diagnostics` to the CLI:

```console
clean-ioc profile my_app.composition:application_builder --diagnostics --format json
```

Pass a fresh `CompilationProfiler` to either builder's `build()` method:

```python
from clean_ioc import CompilationProfiler

profiler = CompilationProfiler(max_records=10_000)
try:
    container = application_builder().build(profile=profiler)
finally:
    print(profiler.report().to_text())
```

The report remains available when the build fails. It records one build, including blueprint preparation, alias and
boundary preparation, decorator-template expansion, primary compilation, build-mode validation, and any diagnostic
root retries. A used collector cannot be attached to another build. The builder can still be repaired after a failed
build with a fresh collector. `to_json()` returns an unversioned, deterministic serialization of the captured report;
durations vary between runs and never enter graph manifests or fingerprints.

The CLI takes an unbuilt builder or a zero-argument factory returning one:

```bash
clean-ioc profile my_app.composition:application_builder --format text
clean-ioc profile my_app.composition:application_builder --format json -o compilation-profile.json
```

It runs exactly one public build. A successful build exits `0`, a failed build emits its partial profile and exits `1`,
and invalid targets, limits, or output paths exit `2`. Built containers and scopes cannot be profiled retroactively.
The measured interval begins at `build()`; module import, builder-factory execution, prior registration work, and
parent builds reused by an overlay are excluded. Registered activation factories, constructors, resolution, and
validation-only rules are excluded too. Explicit argument derivations and decorator-template factories are composition
callbacks and are included. For all rules, run `check` separately.

Phase durations do not overlap. Nested span `inclusive_ns` includes child work; `self_ns` excludes it. The `other build
work` phase includes finalization and runtime wrapper construction that has no separate top-level phase. Counters name
their measured units: specialization requests are distinct from materializations, graph occurrences from returned
candidate plan steps, and anchored parent plan reuse from fresh compilation. Factory specialization counts cover
factory registrations specifically; other generic work appears in candidate timing and graph occurrences. A detailed-span limit does not stop phase
timing or work counts. When records are omitted, the displayed hotspots describe retained samples only; omitted child
time remains excluded from a retained parent's self time. Reports contain semantic class/function labels and no
configured values, build-input names, arbitrary representations, or runtime IDs.
Each retained declaration span has a recording-local `definition_ref`, so two declarations using the same implementation
remain distinct in the costly-definition summary. These references are sequential and have no meaning across builds.

A slow registration predicate appears as a `selection callback` span under its candidate's build phase. Its self time
helps locate callback cost; the selection callback count shows how many times it ran, without rerunning it. A pattern
that expands across many dependencies may show modest time per candidate but high `candidate compilation attempts`
and `graph occurrences`. Inspect those counts alongside `factory specialization requests` and `materializations` to
distinguish repeated lookups from new closed plans. Durations include profiler overhead and are diagnostic observations,
not performance thresholds. Use repeated external measurements before deciding whether a change is faster.

In a local smoke measurement on Python 3.14 (25 paired builds per shape), the median enabled/disabled build ratios were
1.05× for 25 independent roots, 1.04× for a 20-level dependency chain, 1.01× for 25 closed generic registrations, and
1.01× for 25 roots with selection predicates. These short runs are noisy and are not a production overhead guarantee;
the disabled path was the current codebase, without a historical baseline comparison.

## Compiler allocation and eligibility counts

`CompilationProfiler(max_records=0)` retains aggregate counts and safe per-definition
`definition_counts`, `registration_counts` and `root_counts` while omitting all spans.
Attribution grows with registered definitions and root labels, rather than the
number of candidate attempts. Registration IDs separate multiple uses of one implementation.
Counts distinguish definitions considered, candidate compilation entries, actual
registration subplan compilation, early exclusions, retained early rejection records,
invariant subplan cache hits, unique/reused activation templates, physical component
records, provider adapters and provider target view contexts. `candidate compilation
attempts` includes early cache lookups; `registration subplans compiled` counts admitted
registration bodies that compile dependencies. The per-definition `subtrees compiled`
aggregate likewise records actual compilation; `subplans reused` records early hits.
`graph occurrences` counts physical component records plus view contexts, matching
`CompilationBudget.graph_occurrences`. Logical graph visits may exceed that count.

Activation templates are interned only after full per-occurrence validation and
selection. Equivalence requires the same actual registration and layer, closed type
binding, step type, runtime owner, cleanup descriptor and selected dependency-step
identities/names. Decorated, configured, provider-map and per-call targets bypass
interning. This shares immutable executable plans without merging runtime caches.
`reused activation templates` counts these post-compilation interning hits separately
from `invariant subplan cache hits`.

A compiler-local early cache additionally reuses successful subplans whose entire
compilation reaches only invariant work. A transitive proof rejects contextual or
opaque selection/derivation callbacks, preferences, boundary projections, runtime
context, slots, providers, provider maps, per-call plans, anchored descendants,
resolution requests, decorators and pre-configurations, including rejected pipeline
callbacks. Keys retain registration/layer and closed type identities, composition
area, retention owners and deferred boundary kind. Cached registration footprints
cannot intersect the active stack. Ancestor captive checks precede reuse, and plans
with cleanup owners outside their subtree are excluded.

Early reuse clones fresh occurrence records, remaps parent/argument/owner references,
and shares immutable executable/diagnostic payloads. Physical graph records still
count toward the budget, and cloning checks the complete logical depth. Runtime
profiling binds separate observations to each graph occurrence. Selection history
and failed-build census remain records of actual evaluation; cached descendants do
not fabricate new selection attempts. Inspection and validation use the remapped
occurrence paths. See [invariant subplan evidence](invariant-subplan-evidence.md)
for allocation measurements and the conservative fallback contract.

Frozen explanation mappings transfer into the inspection graph without a second
copy. Argument occurrence references stay compact until `explain_arguments` renders
paths. Explanation lookups share a graph-owned occurrence-to-path index, built
lazily once per selected view. Entry-point paths retain precedence over all-root
paths, while argument references retain their all-root spelling. The index retains
occurrence IDs and path strings rather than component projections. Ownership/captive
validation still runs during compilation; the richer
`ownership_report()` presentation and path index are allocated only on request.
Generic maps are inspected lazily using typetoolbox's read-only mapping API. Freezing
releases drafts as records are created, and successful builds release compiler caches.

See [compiler memory evidence](compiler-memory-evidence.md) for measurements and
remaining application/deployment work. `benchmarks/compiler_memory_evidence.py`
reports retained physical record/context counts and shallow storage separately from
fresh-process RSS and profiled operation counts. Shallow storage is a lower bound,
not a retained heap measurement. Do not compare profiled timing against normal builds.
