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

analysis = builder.analyse()
print(analysis.report.to_text())
print(analysis.graph.to_text())
```

`root_policy` classifies each registration:

| Policy | Build and resolution behavior |
| --- | --- |
| `"entrypoint"` | Public root, also marked for the focused graph view. |
| `"resolvable"` (default) | Public root without a tooling marker; this is the existing registration behavior. |
| `"dependency_only"` | Available to dependencies, but not directly resolvable as a root. An unused registration is discarded by default. |

`analyse()` retains and validates unused dependency-only declarations for inspection, without exposing public resolution roots. Production builds omit unused declarations; a broken dependency in an omitted orphan does not fail startup.

`mark_entrypoint()` remains available for request-level markers, such as a filtered selection or `list[MessageHandler]`. An entry-point marker focuses tooling; it does not change a registration's root policy. Once any entry point is marked, registrations outside all marked component trees produce `unreachable-component` warnings.

Mark a collection when every implementation is an application entry point:

```python
builder.mark_entrypoint(list[MessageHandler])
```

<a id="optional-explanation-metadata"></a>
<a id="optional-diagnostic-capture"></a>
<a id="deferred-reachability-advisories"></a>
<a id="failure-aggregation"></a>

<a id="run-and-analysis-modes"></a>

## Build and analyse

`builder.build()` emits an ordinary execution runtime. It performs the binding and emission needed for execution,
but runs no custom validation rules, policy checks or safety audit. Impossible binding still fails locally with
`ContainerBuildError`. Actual resolution, scope ownership, async and cleanup guards remain enforced.

`builder.analyse()` returns a completed `AnalysisResult`: its immutable `AnalysisReport`, full or partial graph,
coverage and stage/rule outcomes. Every available validation declaration runs once before return. A missing graph
makes graph-dependent rules unavailable; cancellation or a budget can make the result incomplete. An incomplete
report is never valid. Reading reports, graphs, census or triage does not replay callbacks.

```python
with application_builder().analyse() as analysis:
    analysis.report.assert_valid()
    print(analysis.graph.manifest(all_roots=True).to_json())
    with analysis.create_runtime() as runtime:
        runtime.resolve(Application)
```

`create_runtime()` uses the emitted test plan without recompilation. A result may have an executable plan despite
policy errors; callers decide whether to test it. If emission failed, runtime creation raises
`AnalysisRuntimeUnavailableError`. The result closes its test runtimes in reverse creation order, never a borrowed parent.
Production separately calls a fresh composition factory's `build()`.

Each admitted attempt consumes its builder on success, failure, cancellation or budget refusal. Retry with a fresh
builder. Invalid inputs rejected before admission leave the builder mutable. Analysis can make independent diagnostic
root attempts after binding failures; those can repeat wiring callbacks, but never validation declarations.

CLI checks and inspection commands and matrix variants call `analyse()` once. They accept an unbuilt builder,
a factory returning one, or a completed result where appropriate. Incomplete or invalid analysis exits unsuccessfully.
Compilation profiling selects `--operation build|analyse`, defaulting to `build`.

### RC migration

`BuildMode`, `ValidationRuleMode`, `BuildReport`, `build(mode=...)`, per-rule phases and fine-grained build flags are
removed. Use `AnalysisReport` and the two named operations. Runtimes have no `graph`, `build_report`,
`validation_report`, `build_mode`, `explain_metadata_enabled`, `allow_scope_builders` or `new_scope_builder` API.
`build_args`, `budget` and `profile` apply to either operation; execution instrumentation belongs to `build()` or
`result.create_runtime()`.

### Declared provider roots

Declare public handles before building with `builder.set_provider_roots(...)`.
The declaration is independent of mode. `None` (the default) enables all automatic
provider families and collection forms. An empty iterable enables none. Marked
provider entrypoints are always included; injected handles and provider maps keep
their dependency-specific targets.

```python
from clean_ioc import AsyncProvider, ContainerBuilder, Provider

builder = ContainerBuilder()
builder.register(PaymentGateway, StripeGateway)
builder.set_provider_roots((AsyncProvider[PaymentGateway], Provider[list[PaymentGateway]]))
analysis = builder.analyse()
```

The iterable is captured immediately, aliases normalized and duplicates removed.
Repeated calls replace the declaration; invalid declarations leave the previous
one intact. Scope builders have their own declaration, initially `None`; they do
not implicitly inherit a parent's restricted handle surface. Private managed
acquisition targets remain compiled when necessary, without becoming public roots.
Discovery never requires expanding public roots.

### Runtime discovery and evidence lifetime

`selected_registrations` remains a complete frozen catalogue of selected executable
registrations and decorators, including dependency-only and deferred targets.
It preserves IDs, canonical visible service types, implementation types, names
and tags. It excludes rejected candidates, unused dependency-only declarations,
synthetic nodes and unexposed architecture-only roots. Reading never resolves,
compiles or reruns callbacks. Ordinary child scopes share the tuple; compiled
overlays receive their own selection catalogue.

Runtime components retain the relationships required by filters, providers, provisions and cleanup. Runtimes do not
retain diagnostic histories or a link to an analysis result. Keep analysis results only where inspection is needed.

### Overlay composition

Retain external composition before compiling when overlays will be needed:

```python
from clean_ioc import ScopeBuilder

builder = application_builder()
composition = builder.retain_composition()
with builder.build() as parent:
    child_builder = ScopeBuilder(parent, composition=composition)
    child_builder.register(Service, Replacement)
    with child_builder.build() as child:
        child.resolve(Service)
```

Analysis results automatically expose `result.composition` after executable capture. The handle contains immutable
library declarations and retains opaque application values by identity; it has a retained-memory cost. It has no
close or context-manager lifecycle. A child builder requires the matching live parent lineage and owns its restored
declarations. Ordinary `new_scope()` needs no handle. Parent singletons keep their original owner and activation step;
a new compilation can rerun template factories, but handle/report/runtime reads never do.

### Analysis-only roots

Analysis validates unused dependency-only declarations without exposing them to
`resolve()`. Invalid unused declarations can therefore fail analysis while run
succeeds. Graph roots expose `resolvable`; manifests mark nonpublic roots with
`"resolvable": false`, and text rendering labels them `Inspect`. Promoting one
of these declarations to a public root remains visible in semantic graph diffs.
The selected executable catalogue is unaffected by these inspection-only roots.

## Completed reports and partial analysis

`AnalysisResult.report` contains findings, `complete`, root coverage, and rule/stage outcomes. It is available even
when no full graph could be emitted. Production binding errors are local errors without rich reports or partial graphs.

```python
result = builder.analyse()
for issue in result.report.errors:
    print(issue.code, issue.path, issue.message)
if result.partial_graph is not None:
    print(result.partial_graph.to_text())
print(result.triage_report().to_text())
```

A partial graph is frozen, non-executable diagnostic evidence. It records completed branches, failed parameter edges,
known candidates and bounded independent attempts. `not-examined` differs from rejected; cycles have explicit
back-references. Counts report retained and omitted evidence. Diagnostic attempts are not merged into a coherent
execution graph. Analysis never activates application constructors.

```console
clean-ioc graph my_app.composition:application_builder --on-error partial --format json -o failed-graph.json
clean-ioc check my_app.composition:application_builder --triage --format json
```

`result.triage_report()` groups supported failures from captured evidence and preserves references into the completed
report. `result.selection_census()` returns the full inventory when available or an honest lower-bound failed census.
Repeated reads do not compile, run rules or replay selection.

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
strictness, and warning-suppression behavior as compiler findings. Rules use `add_validation_rule(rule)` and run once during `analyse()`. Report reads do not rerun them. Use
`context.graph.walk()` for a deterministic all-roots traversal; each returned `GraphVisit` retains the component objects
and the matching diagnostic path. See [Custom graph validation](custom-validation.md) for the complete rule cookbook.

## Render the compiled graph

The graph includes registrations and activation edges for decorators, pre-configurations, default and configured values,
runtime contexts, and declared scope slots. Decorator pipelines render outside-to-inside with their
positions and metadata. Nodes describe components; edges consistently describe their relationship as
`depends on: <argument>`, `decorated by`, or `pre-configured by`.

```python
text = analysis.graph.to_text()
mermaid = analysis.graph.to_mermaid()
manifest = analysis.graph.manifest()
ownership = analysis.graph.ownership_report()

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
difference = analysis.graph.manifest().diff(baseline)

for change in difference.changed:
    print(change.path)
```

Manifests include `cache_owner`, `cleanup_owner`, and a semantic `owner_path` on every node. A diff reports added,
removed, and semantically changed component paths and boundary contracts.

Use `analysis.graph.diff(baseline)` for classified changes with known current entry points, and
`difference.evaluate(DiffPolicy(...))` to enforce risk thresholds, denied kinds, and path allowances.
See [Graph-change policies](graph-change-policies.md) for complete Python and CLI examples.

[Build-variant matrices](build-matrices.md) compile an explicit set of supported configurations, aggregate each
variant's completed analysis findings, and apply entry-point and semantic-drift policies against a named reference.
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
impact = analysis.graph.dependents(PaymentGateway, match="registration")
print(impact.to_text())

sharing = analysis.graph.sharing_report(Database)
print(sharing.to_json())

activation = analysis.graph.activation_report(Checkout, scenario="cold")
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

default = analysis.graph.explain(PaymentGateway)
stripe = analysis.graph.explain(
    PaymentGateway,
    filter=cf.with_name("stripe"),
)

gateway = next(
    dependency
    for dependency in checkout_component.dependencies
    if dependency.service_type is PaymentGateway
)
dependency_choice = analysis.graph.explain(gateway)
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
component = analysis.graph.component_at_path(
    "root:my_app.Checkout:default:0/dependency:serializer:0"
)
for parameter in analysis.graph.explain_arguments(component):
    print(parameter.parameter, parameter.policy_kind, parameter.result_category)

specialization = analysis.graph.explain_specialization(component)
print(specialization.service_bindings)
print(specialization.factory_pattern_bindings)  # a distinct TypeVar scope
```

`build_arg(...)` is identified as an explicit build input but its key and value are never exposed. `generic_arg(...)`,
`derive(...)`, `inject()`, `select()`, fixed arguments, Python defaults, and implicit injection remain distinct policy
kinds. Generic records preserve before/after dependency annotations and keep service and structural factory-pattern
bindings separate. They are compiler evidence, not a new runtime type check. `ParameterExplanation.to_dict()` omits
provenance by default so equivalent builds serialize identically; pass `include_provenance=True` when source metadata is
needed for an interactive or local report.
Only successful specializations have a graph occurrence and therefore a `GenericBindingExplanation`; an incomplete
analysis exposes its captured redacted selection/failure explanations instead of reconstructing bindings by re-running
user code.

## Reverse dependencies and impact

`graph.dependents(...)` builds a lazy, immutable sidecar index from the compiled plan. It does not run constructors,
factories, filters, or argument policies, and it leaves manifests and their fingerprints unchanged. Select a concrete
occurrence when its path matters, or select one registration to include every compiled occurrence of that registration:

```python
impact = analysis.graph.dependents(PaymentGateway, match="registration")
for root in impact.affected_entrypoints:
    print(root.path, impact.witness_paths[root.path])

# Provider targets are a separate deferred edge category.
including_deferred = analysis.graph.dependents(
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
report = builder.analyse().graph.selection_census()
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
The compiler never reruns a predicate, derivation, key function, or template callback for this report. An incomplete analysis
offers `result.selection_census()` with `complete=False`: selected, rejected, failed, and not-examined evidence from its
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
`census` emits text or JSON and exits `0` even with zero selections. If analysis is invalid or incomplete, it emits the captured census and
exits `1`; invalid input or output exits `2`.
`impact`, `sharing`, and `activation` emit text, JSON, or Mermaid and exit `2` for invalid targets, paths, or ambiguous
selectors. Impact analysis is informational; high fan-in does not fail a build.
`explain` exits `0` for an explanation, `1` when analysis is invalid or incomplete, and `2` for an invalid target, service,
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

Profiling defaults to `build`. Select `analyse()` in Python or `--operation analyse` to profile analysis:

```console
clean-ioc profile my_app.composition:application_builder --operation analyse --format json
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
boundary preparation, decorator-template expansion, primary compilation, analysis validation when selected, and any diagnostic
root retries. A used collector cannot be attached to another build. A failed builder is consumed; use a fresh builder and collector. `to_json()` returns an unversioned, deterministic serialization of the captured report;
durations vary between runs and never enter graph manifests or fingerprints.

The CLI takes an unbuilt builder or a zero-argument factory returning one:

```bash
clean-ioc profile my_app.composition:application_builder --format text
clean-ioc profile my_app.composition:application_builder --format json -o compilation-profile.json
```

It runs exactly one selected public operation. A successful build exits `0`, a failed build emits its partial profile and exits `1`,
and invalid targets, limits, or output paths exit `2`. Built containers and scopes cannot be profiled retroactively.
The measured interval begins at `build()`; module import, builder-factory execution, prior registration work, and
parent builds reused by an overlay are excluded. Registered activation factories, constructors, resolution, and
validation rules are excluded from build and included in analyse. Explicit argument derivations and decorator-template factories are composition
callbacks and are included. Use `check` for a completed validation report.

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
from `invariant subplan cache hits`. `unique activation templates` counts cache
admissions, including a new generation when a discarded scalar-only plan is later
recreated. It is not a count of simultaneously live plans or structurally distinct
keys. Optional scalar-only templates may use weak ownership; opaque values and
unsupported key or execution forms keep strong ownership through compilation.

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
