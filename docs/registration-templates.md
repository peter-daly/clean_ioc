# Registration templates

A registration template creates one ordinary registration for each selected source registration at `build()`.
Use it when every registered event source needs its own worker, or every configured backend needs its own adapter.
The API follows [decorator templates](decorator-templates.md): an exact `for_each` service key, an optional
`source_filter`, and a synchronous factory receiving frozen `RegistrationInfo`.

## One worker per source

This complete example binds each worker to its specific source registration:

```python
from clean_ioc import ContainerBuilder, RegistrationTemplate, select
from clean_ioc import component_filters as cf


class EventSource:
    def __init__(self, label: str):
        self.label = label


class Worker:
    def __init__(self, source: EventSource):
        self.source = source


builder = ContainerBuilder()
orders = EventSource("orders")
payments = EventSource("payments")
builder.register(EventSource, instance=orders)
builder.register(EventSource, instance=payments)


def worker_for(source):
    return RegistrationTemplate(
        service_type=Worker,
        arguments={"source": select(cf.with_id(source.id))},
    )


template_id = builder.register_registration_template(
    for_each=EventSource,
    template=worker_for,
)
with builder.build() as container:
    workers = container.resolve(list[Worker])
    assert len(workers) == 2
    assert {worker.source for worker in workers} == {orders, payments}
```

`source.id` identifies a registration. Two registrations using the same class still produce two workers.
The exact ID selection prevents both workers from receiving whichever source wins ordinary default selection.
Sources and workers follow their declared lifespans; one generated registration does not imply one instance.

## One generated dependency per source

The source can also depend on the registration generated for it. Here each `X` receives a `Y` configured from that
specific `X` registration's name:

```python
from clean_ioc import ContainerBuilder, RegistrationTemplate
from clean_ioc import component_filters as cf


class Y:
    def __init__(self, label: str):
        self.label = label


class X:
    def __init__(self, y: Y):
        self.y = y


builder = ContainerBuilder()
builder.register(X, name="first")
builder.register(X, name="second")
builder.register_registration_template(
    for_each=X,
    template=lambda source: RegistrationTemplate(
        service_type=Y,
        arguments={"label": source.name},
        when=cf.parent(cf.with_id(source.id)),
        root_policy="dependency_only",
    ),
)
with builder.build() as container:
    first = container.resolve(X, filter=cf.with_name("first"))
    second = container.resolve(X, filter=cf.with_name("second"))
    assert first.y.label == "first"
    assert second.y.label == "second"
```

`when=cf.parent(cf.with_id(source.id))` makes each generated `Y` eligible only beneath its matching `X` registration.
`root_policy="dependency_only"` keeps these contextual dependencies out of direct root resolution. Registration
expansion happens before dependency compilation, so `X` can require a `Y` that does not exist until its template runs.
Both dependency directions can coexist in a composition, for example `Adapter -> X -> Y`. Ordinary cycle and lifespan
validation applies to the completed graph.

## Source selection and factory results

`for_each` selects one exact, closed service key. `EventSource` enumerates registrations under `EventSource`;
a subclass registered only under its own service key is excluded. A closed generic such as `Store[Image]` is accepted;
an open generic such as `Store[T]` is rejected. Zero matching sources produce zero registrations.

`source_filter` receives a parentless `Component` with static registration metadata and build arguments. Reading
IDs, service and implementation types, names, tags, or lifespans does not compile the source's dependencies. This lets
metadata filters select sources that need their generated services before they can be compiled.

A filter that reads graph properties, such as `dependencies`, `has_descendant(...)`, ownership, or async requirements,
requests the complete undecorated source graph on demand. That inspection uses the original source inventory, excluding
generated registrations. Such a filter still needs the source to be compilable before expansion. If it cannot be,
build raises `registration-template-source-graph`: use registration metadata for source selection and the returned
registration's `when` for conditions evaluated during normal compilation. Requested inspection graphs are frozen;
a captured source view cannot start a new graph inspection after its filter returns.

The factory runs only for selected sources. It receives `RegistrationInfo` with `id`, `service_type`, `implementation_type`, `name`, and tuple `tags`.
`implementation_bindings(Base)` supports the same static generic projection as decorator templates.

Return a `RegistrationTemplate` synchronously. Its fields match `register(...)`: `service_type`,
`implementation_type`, `factory`, `factory_specialization`, `instance`, `arguments`, `lifespan`, `scope`, `name`,
`tags`, `when`, `parent_precedence`, `prefer`, `contributes`, `groups`, and `root_policy`.
Arguments, tags, groups, and contribution mappings are copied into immutable containers.
The result goes through ordinary registration validation.

Binding the source as a dependency is optional. A template can use source metadata to choose the generated service,
implementation, name, tags, or configured values. The source filter chooses whether to generate a registration;
the returned `when` controls where that generated registration may be selected as an ordinary dependency.

## Build order and runtime behavior

Discovery materializes first. Registration templates then enumerate the same source snapshot, in declaration order
within each visible layer. Generated registrations do not become sources for registration templates, including in
overlays. This prevents recursive expansion and makes template declaration order independent of generated inputs.
Metadata source selection completes before normal dependency compilation. Structural source filters inspect the
pre-expansion graph; they do not observe generated dependencies.

Generated registrations are added after explicit and discovered registrations. Within a layer they therefore take
ordinary newest-first selection precedence; later templates and later sources take precedence over earlier ones.
Use names, filters, or collections when several registrations share a service key.

Decorator templates expand afterward. They can use generated registrations as sources or decorate them as targets.
Ordinary decorators, group memberships, provider-map contributions, dependency validation, scope ownership, and cleanup
apply to generated registrations. Build does not instantiate sources or generated services. Runtime resolution executes
the frozen plan and never calls template factories or source filters.

## Edits, scopes, and boundaries

`register_registration_template(...)` returns the declaration ID. Before build succeeds, use
`patch_registration_template(template_id, for_each=..., template=..., source_filter=...)` to replace specified fields,
or `remove_registration_template(template_id)` to remove the declaration. Unknown and removed IDs raise `KeyError`.
A failed build leaves the builder repairable; a successful build freezes it. Callbacks must not mutate or reenter
composition. Keep them pure: previews and failed-build retries may run them again.

An overlay inherits existing generated registrations with their original owners. Their source selection and
registration specification remain frozen; the overlay does not rerun their filters or factories. An inherited template
can generate additional overlay-owned registrations for newly selected sources. A parent singleton retains its parent
activation plan.

Patching an inherited template replaces its generated registrations in the overlay with new overlay-owned definitions.
Removing it removes its generated registrations from overlay selection. Neither operation changes the parent container
or rewires dependencies already captured by a parent singleton. Inherited private boundaries retain their frozen
source selections and outputs. A plain `new_scope()` reuses the frozen plan.

A boundary template sees only local and explicitly imported source registrations. Its generated registrations belong
to that boundary and may be exposed through ordinary `Expose(...)` declarations. Root templates cannot enumerate
private sources. Boundary exposure and use declarations are validated again after registration expansion. If expansion changes a
template's source visibility, build fails rather than applying the template to a different source set.

## Inspection

`container.graph.explain_template_sources(template_id)` returns captured source decisions, including the source
registration ID and generated registration ID. Generated registrations appear in the ordinary graph and selection
census, with their declaration origin and source/template references. Inspection does not replay callbacks.
Build errors identify the template and source when expansion fails; ordinary graph validation checks generated edges.
