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
builder.register(Checkout)
builder.mark_entrypoint(Checkout)

container = builder.build()
print(container.build_report.to_text())
print(container.graph.to_text())
```

An entry point changes the default tooling view, not compilation or resolution. Clean IoC still compiles and validates every visible root, and an unmarked root remains resolvable. Once any entry point is marked, registrations outside all marked component trees produce `unreachable-component` warnings.

Mark a collection when every implementation is an application entry point:

```python
builder.mark_entrypoint(list[MessageHandler])
```

## Structured build reports

A successful runtime exposes its immutable `BuildReport` as `container.build_report`. A failed build raises `ContainerBuildError` with the same report on `error.report`.

## Inspect a failed build

Failed builds also expose `error.partial_graph`: a frozen, non-executable diagnostic snapshot. It records only
structural labels, completed draft branches, observed failing parameter edges, and known selection candidates.
Evaluated candidates are marked `complete`, `failed`, or `rejected`; known candidates compilation did not visit are
marked `not-examined`, never rejected. Cycles use explicit back-reference edges and attempts
retain their safe witness paths. It deliberately does not freeze a
runtime graph, execute constructors or callbacks, or serialize configured values or exception text.

```python
from clean_ioc import ContainerBuildError

try:
    builder.build()
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
When compilation reached candidate selection before failing, `ContainerBuildError.explanations` contains the safe partial
decision records captured up to that point; retrying the repaired builder creates a fresh index.

Current issue codes include:

- `missing-component`, `missing-entrypoint`, and `ambiguous-selection`;
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

Graph manifests, build reports, and ownership reports are unversioned during beta. They omit schema version fields,
and readers use the current format without version checks or migration adapters. Regenerate saved graphs and baselines
when the format changes. Schema versioning will begin after beta. Deterministic ordering and redaction still apply.

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
clean-ioc graph my_app.composition:application_builder --format mermaid
clean-ioc graph my_app.composition:application_builder --format json -o dependency-graph.json
clean-ioc ownership my_app.composition:application_builder --format json
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

`diff` exits `0` when the graph is unchanged and `1` when it changed. Add `--all` to `graph` or `diff` when the baseline should include every root rather than the entry-point view. Baselines are never updated implicitly.
`ownership` emits the frozen all-roots ownership proof as text or JSON and does not activate components.
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
