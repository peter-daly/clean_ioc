# Policy helpers and packs

A policy helper creates an ordinary `ValidationRule`: a synchronous callback that checks the compiled graph and yields
`BuildIssue` findings. Register it with `add_validation_rule()` or group rules in a `PolicyPack`. Both use the existing
[build and explicit-validation phases](validation.md#custom-graph-rules).

## A pack with build and validation rules

Pass a list of callbacks to `PolicyPack(name, rules)`. Plain callbacks use the pack's default `mode="build"`. A
`(callback, "build")` or `(callback, "validation")` entry selects the phase for that individual rule. The list is copied
to an immutable tuple when the pack is created.

This complete example requires tracing during startup and checks ownership during explicit validation:

```python
import clean_ioc.component_filters as cf
from clean_ioc import ContainerBuilder, Tag
from clean_ioc.policies import PolicyPack, require_decorator, require_tags


class PaymentGateway:
    pass


class TracedGateway(PaymentGateway):
    def __init__(self, inner: PaymentGateway):
        self.inner = inner


gateways = cf.service_type_is(PaymentGateway)
policies = PolicyPack(
    "payments",
    [
        require_decorator(gateways, decorator_type=TracedGateway),
        (require_tags(gateways, Tag("owner", "payments")), "validation"),
    ],
)

builder = ContainerBuilder()
builder.register(PaymentGateway, tags=(Tag("owner", "payments"),))
builder.register_decorator(
    PaymentGateway,
    TracedGateway,
    decorated_arg="inner",
    tags=(Tag("owner", "payments"),),
)
builder.apply_bundle(policies)
container = builder.build()
report = container.validation_report()
report.assert_valid()
```

Custom callbacks work in the same list. Use `(inspect_implementation_source, "validation")` for an expensive AST rule.
Set `PolicyPack(..., mode="validation")` to make plain callbacks validate-only, and use `(rule, "build")` for any startup
check in that pack.

`build()` runs build rules and fails on their errors. `validation_report()` retains the stored build findings and runs
validate-only rules once per call; it does not rerun build rules. The strict-by-default `clean-ioc check` command uses
the same complete report. Custom warnings retain their severity, and `--ignore CODE` suppresses warnings only.

Packs are callable bundles for root, scope, and boundary builders. Existing rule inheritance and boundary visibility
apply: scope overlays inherit parent rules and run local rules afterward, while boundary-local rules inspect the graph
visible to that boundary. Pack names are included in finding messages. Neither packs nor policy findings change graph
manifests or fingerprints.

## Available policy types

Import these factories from `clean_ioc.policies` or directly from `clean_ioc`:

| Factory | Checks | Configuration |
| --- | --- | --- |
| `layering` | Allowed direct implementation-layer dependencies | `layers`, `allowed_dependencies`, optional `require_match` |
| `forbid_dependency` | Prohibited source-to-target dependencies | Source and target filters; optional `transitive=True` |
| `require_decorator` | Exact decorator type and count on service registrations | Target filter, `decorator_type`, optional `count=1` |
| `require_lifespan` | Allowed public lifespans on matching occurrences | Target filter, one or more lifespan strings |
| `forbid_runtime_access` | `Scope` (including `Container`) or `ResolutionContext` dependencies below selected components | Target filter |
| `require_tags` | Exact required tag name/value pairs on matching occurrences | Target filter, one or more `Tag` objects |
| `capability_boundary` | Allowed declared capabilities across entry-point dependency trees | Entry-point filter, `allow` iterable |

Filters use the immutable `Component` model. Apart from `require_decorator`, which selects registration nodes, matching
can include decorators, pre-configurations, and synthetic nodes. Use a custom predicate on `component.kind` when a
metadata or lifespan convention should cover only registrations.

## Dependency paths

Dependency rules inspect the complete occurrence graph, including unmarked roots, decorator dependencies,
pre-configurations, collections, argument selection, and deferred provider targets. Collections, providers, provider
maps, and per-call handles are transparent to direct checks. An intermediate service registration requires
`transitive=True`.

`forbid_dependency` and `forbid_runtime_access` produce at most one finding per selected source occurrence, pointing to
the shortest forbidden path. If a registration appears below several roots, each violating occurrence is reported.
Custom matcher exceptions or non-boolean results become `validation-rule-error`; later rules continue running.

## Implementation layers

`Layer("application", module_prefixes=("my_app.application",))` matches an implementation's exact module and its
submodules. It does not match `my_app.application_extra`. More specific prefixes take precedence over broader ones.
Layer names and prefixes must be unique. The dependency map references declared layer names; a missing source entry
allows no dependencies. Unmatched implementations are ignored unless `require_match=True`. Synthetic bridge and value
nodes do not need layer declarations.

Factories use the compiler's known implementation type; pre-configurations use the configuration callback's module.

Layering checks the implementations wired together, so a handler receiving a repository interface can have a compiled
edge to an infrastructure implementation. Include that intended relationship in the map. Python import direction and
interface ownership are separate concerns that can be checked with custom source rules.

```python
from clean_ioc.policies import Layer, layering

architecture = layering(
    layers=[
        Layer("application", module_prefixes=("my_app.application",)),
        Layer("adapters", module_prefixes=("my_app.infrastructure",)),
    ],
    allowed_dependencies={
        "application": {"application", "adapters"},
        "adapters": {"adapters"},
    },
)
builder.add_validation_rule(architecture)
```

## Exact decorators, tags, and capabilities

`require_decorator` checks the compiled pipeline after decorator selection. Closed generic types match exactly:
`TracedHandler[int]` does not match `TracedHandler[str]`. Transparent type aliases are normalized. `count=0` forbids that
decorator. This helper validates composition without activating the decorator.

`require_tags` compares exact `Tag` pairs. `Tag("owner")` requires a tag whose value is exactly `None`; use
`cf.has_tag("owner")` in a custom rule to require any owner value instead. Missing required tags are collected into one
finding per matching occurrence.

`capability_boundary(entrypoints, allow={"database"})` selects marked entry points using its filter. Without entry-point
markers, it selects from all compiled roots. Capabilities accumulate from root tags and every dependency, decorator,
pre-configuration, and deferred target. An entry point receives one finding listing its forbidden capabilities in
sorted order.

Capabilities come only from explicit `Tag("capability", "network")` metadata. A capability tag with no value declares
no capability. Class names, imports, and runtime effects are not inspected.

## Finding codes

Factories yield errors with stable codes:

- `policy-layer-violation`
- `policy-unmatched-layer`
- `policy-forbidden-dependency`
- `policy-missing-decorator`
- `policy-decorator-count`
- `policy-invalid-lifespan`
- `policy-runtime-access`
- `policy-missing-tag`
- `policy-capability-violation`

Policy configuration is validated before registration. Invalid counts, lifespans, layers, filters, pack entries, or
phase names raise `TypeError` or `ValueError`. Callback failures during validation use the existing structured
`validation-rule-error` finding.

Export policy findings with `clean-ioc check ... --format sarif -o clean-ioc.sarif` for source-linked CI review.
See [Source-linked CI reporting](sarif.md) for registration locations, dependency paths, and GitHub upload configuration.
