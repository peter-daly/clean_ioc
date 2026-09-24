# Decorator templates

A decorator template builds a policy from registered sources. At `build()`, Clean IoC finds registrations for one **exact, closed** `for_each` service key, tests each source, and calls a synchronous factory once for each selected source registration. The factory returns a `DecoratorTemplate`: a decorator, its target selector, and ordinary decorator options. The compiler then applies that definition to eligible target occurrences. This is useful when a decorator needs one specifically configured audit sink, policy, or other source registration.

Use [ordinary decorators](decorators.md) when one fixed definition is enough. Both forms produce frozen decorator plans; neither creates runtime registrations by resolving a source during composition.

## One source, one target

This complete program uses only Clean IoC and the standard library:

```python
from clean_ioc import ContainerBuilder, DecoratorTemplate, DerivedServices, select
from clean_ioc import component_filters as cf


class AuditSink:
    def __init__(self):
        self.events: list[str] = []

    def record(self, event: str) -> None:
        self.events.append(event)


class Stage:
    def run(self, text: str) -> str:
        return text.upper()


class AuditedStage(Stage):
    def __init__(self, inner: Stage, sink: AuditSink):
        self.inner = inner
        self.sink = sink

    def run(self, text: str) -> str:
        self.sink.record(text)
        return self.inner.run(text)


builder = ContainerBuilder()
sink = AuditSink()
builder.register(AuditSink, instance=sink)
builder.register(Stage)


def audit_for(source):
    return DecoratorTemplate(
        services=DerivedServices(Stage),
        decorator_type=AuditedStage,
        arguments={"sink": select(cf.with_id(source.id))},
    )


template_id = builder.register_decorator_template(
    for_each=AuditSink,
    template=audit_for,
)
with builder.build() as container:
    assert container.resolve(Stage).run("hello") == "HELLO"
    assert sink.events == ["hello"]
```

`source.id` is the source **registration ID**. `select(cf.with_id(source.id))` binds the decorator's `sink` argument to that exact registration, even if several registrations have the same service and implementation class. Selecting by class or name alone would not make that guarantee. `inner` is the decorated `Stage`, inferred from its annotation; set `decorated_arg="inner"` if inference needs to be explicit. The returned `template_id` identifies the whole template declaration and can be used for edits and diagnostics.

The factory receives a frozen `RegistrationInfo` with `id`, `service_type`, `implementation_type`, `name`, and tuple `tags`. For a callable whose result type cannot be established statically, `implementation_type` may be `None`. The factory should use static metadata and return `DecoratorTemplate` synchronously. It must not resolve a source or mutate the builder. The specification also accepts `decorated_arg`, `arguments`, `when`, `position`, `name`, and `tags`, just like an ordinary decorator definition.

## Two sources and selective targets

Here both sinks share a class but have distinct registrations. Both decorate the tagged stage; the untagged stage stays plain. The source filter and target predicate inspect different components.

```python
from clean_ioc import ContainerBuilder, DecoratorTemplate, ServiceGroup, Tag, select
from clean_ioc import component_filters as cf


class AuditSink:
    def __init__(self, label: str, events: list[str]):
        self.label = label
        self.events = events

    def record(self, value: str) -> None:
        self.events.append(f"{self.label}:{value}")


class Stage:
    def run(self, value: str) -> str:
        return value


class Trim(Stage):
    def run(self, value: str) -> str:
        return value.strip()


class AuditedStage(Stage):
    def __init__(self, inner: Stage, sink: AuditSink):
        self.inner = inner
        self.sink = sink

    def run(self, value: str) -> str:
        self.sink.record(value)
        return self.inner.run(value)


stages = ServiceGroup("audited-stages", service_type=Stage)
events: list[str] = []
builder = ContainerBuilder()
builder.register(AuditSink, instance=AuditSink("first", events), tags=[Tag("sink", "on")])
builder.register(AuditSink, instance=AuditSink("second", events), tags=[Tag("sink", "on")])
builder.register(Stage, Trim, name="audited", tags=[Tag("audit", "on")], groups=[stages])
builder.register(Stage, Trim, name="plain", groups=[stages])
builder.register(Stage, Trim, name="ungrouped", tags=[Tag("audit", "on")])


def audit_for(source):
    return DecoratorTemplate(
        services=stages,
        decorator_type=AuditedStage,
        arguments={"sink": select(cf.with_id(source.id))},
        when=cf.has_tag("audit", "on"),
    )


builder.register_decorator_template(
    for_each=AuditSink,
    source_filter=cf.has_tag("sink", "on"),
    template=audit_for,
)
with builder.build() as container:
    assert container.resolve(Stage, filter=cf.with_name("audited")).run(" x ") == "x"
    assert events == ["first: x ", "second: x "]
    assert container.resolve(Stage, filter=cf.with_name("plain")).run(" y ") == "y"
    assert container.resolve(Stage, filter=cf.with_name("ungrouped")).run(" z ") == "z"
    assert len(events) == 2
```

`source_filter` receives one canonical `Component` for each source registration. It has no parent and retains its ordinary dependency/build context. Ordinary and generated decorators are recursively excluded. `when` receives each prospective **target occurrence** in its actual undecorated parent context. Its ordinary dependency subtree is present, including descendants; ordinary and generated decorators are recursively excluded there too. Thus `cf.parent(...)` can distinguish targets under different consumers, while a dependency introduced only by another decorator cannot make `when` true. Both are ordinary one-argument [component filters](advanced/filtering.md), evaluated at compilation, not predicates taking source and target together. The factory runs only after a source passes `source_filter`; `when` then decides separately for each target occurrence.

## Explicit membership or registered-contract matching

`ServiceGroup("name", service_type=Stage)` declares an identity and a compatible contract. A target joins through `groups=[stages]` on its **registration**. Another `ServiceGroup` with the same name and contract is a different object and will not share members; bundles should import one shared declaration. Compatible registrations without that exact membership are not selected. Membership can also be passed to `register_pattern`, `register_subclasses`, and `register_generic_subclasses`; discovered registrations inherit the rule's groups when materialized during build.

`DerivedServices(Stage)` instead selects available registrations whose **registered service contract** derives from `Stage`; no `groups=` declaration is required. In the two-source program, replacing `services=stages` with `services=DerivedServices(Stage)` would also decorate the tagged `"ungrouped"` registration. The `"plain"` registration would still fail `when`. Conversely, an implementation subclass registered under an unrelated service contract does not become eligible merely because its class inherits `Stage`. Neither selector creates services, group memberships, map keys, injectable collections, or a `ProviderMapGroup`. [Provider maps](advanced/special-dependency-types.md#explicit-provider-map-groups) are a separate feature with `contributes=` keys. Group membership does not change ordinary service resolution.

For bundles, declare `stages = ServiceGroup("audited-stages", service_type=Stage)` once in a shared module and import that same object into both the registration bundle (`groups=[stages]`) and the policy bundle (`DecoratorTemplate(services=stages, ...)`). For automatic selection, use `DecoratorTemplate(services=DerivedServices(Stage), ...)` and omit `groups=` from target registrations.

Target declarations select among registrations and compiled requests that already exist. They do not discover classes, activate targets, or add new service keys. Queue subclass discovery with `register_subclasses(...)` or `register_generic_subclasses(...)` and, if needed, `ensure_import_modules=` before `build()`. Discovery materializes before template expansion. A successful build is immutable; classes imported afterward need a new builder/build.

## Generic identities and projection

`for_each` must be an exact, closed source service key such as `ResourceStore[Image]`; an open generic key is rejected. The factory's `source.service_type` is that registration's service key. `source.implementation_bindings(Base)` projects a statically known implementation onto a generic base and returns a read-only mapping keyed by that base's actual `TypeVar` objects, or `None` if projection is unavailable. An unknown implementation type is not guessed. This is useful for choosing a target selector or decorator class from source metadata, but the source binding is independent of any target's generic mapping.

For each eligible closed target request, the compiler projects its **registered service contract** onto the `ServiceGroup` or `DerivedServices` contract. It specializes the decorator's wrapped argument and dependencies from the projected target bindings. Source, target, and decorator each retain their own TypeVar identities; same-named TypeVars are not interchangeable. Resolution keeps the originally requested target service key, including a closed alias or implementation lookup key. Ambiguous or unresolved projection fails build with a diagnostic; it does not silently choose a mapping. Ordinary [generic registration rules](generics.md) still determine which closed requests exist.

## Ordering, overlap, and lifecycle

Generated decorators follow the same `position` rule as [ordinary decorators](decorators.md#ordering): higher positions are outside, and equal positions retain earlier registration order from outside to inside. Within one template, sources follow visible registration declaration order (and overlay precedence); in the two-source example, the first declared source is outside, so it records first. Independent templates are additive, even when they choose the same source and target. The compiler adds at most one layer for each template declaration, source registration, and target occurrence combination. Multiple paths to that same occurrence do not multiply that layer, but distinct occurrences can receive distinct layers.

The generated decorator inherits the target core's lifespan and cleanup owner. Its other dependencies compile as ordinary edges, with the usual captive-dependency, cycle, sync/async, and cleanup checks. The source is not instantiated merely to enumerate it. At runtime, resolution follows the frozen plan and does not rerun filters or factories.

## Editing, overlays, and boundaries

`register_decorator_template(...)` returns an ID. Before a successful build, `patch_decorator_template(template_id, for_each=..., template=..., source_filter=...)` can replace specified declaration fields; `remove_decorator_template(template_id)` removes the declaration. Ordinary `patch_decorator(...)` addresses a fixed decorator definition, not a template ID. Unknown or removed template IDs raise `KeyError`. A scope overlay can patch or remove a visible inherited template for its own plan without mutating the parent.

A `Container.new_scope_builder()` overlay compiles a new plan. Newly visible source registrations can add layers to overlay-owned target plans; new eligible targets can receive inherited template layers. A plain `new_scope()` reuses its existing plan. An inherited parent singleton remains anchored to its parent's activation plan and cannot be rewired by an overlay. Templates and source registrations obey boundary visibility: a group object alone does not expose a private registration, and a template cannot use an invisible source. A boundary may declare a template within its private builder for visible local composition, with ordinary explicit exposures/uses controlling cross-boundary access. See [scopes](scopes.md) and [boundaries](boundaries.md).

Filters and factories are pure build callbacks. They can run again for a preview query, an overlay build, or a retry after a failed build; they are not called during ordinary resolution. Avoid side effects and reliance on call counts. A failed build leaves the builder repairable; a successful build freezes it.

## Inspection and errors

After build, `container.graph.explain_template_sources(template_id)` returns frozen source decisions with registration IDs, selection results, source bindings, and a generated definition ID for selected sources. For a target `Component`, `container.graph.explain_decorators(component)` gives selected and rejected decorator decisions; template facts include template/source/target registration IDs, target occurrence ID, selector kind/contract, generic projection, and boundary. `to_text()`, `to_dict()`, and `to_json()` expose captured, value-free explanations. Graph and manifest inspection do not rerun callbacks or reveal configured argument values.

Build reports distinguish an open `for_each` key, source-compilation or callback failure, invalid synchronous factory result, incompatible group contract, unresolved target projection, invalid decorated argument, missing exact source dependency, cycle, and visibility or lifespan failure. `ContainerBuildError` carries structured diagnostics for compilation failures. Registration-time type validation can raise `TypeError`; editing a missing template ID raises `KeyError`. Keep `for_each` closed, make source binding exact, and inspect the captured source and target decisions when a template matches less than expected. Templates operate only on build-time known registrations and requests; they do not provide hot registration or an injectable runtime group/map.
