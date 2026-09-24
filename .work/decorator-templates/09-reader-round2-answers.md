# Fresh reader round 2 — verbatim Phase B

Reader supplied write-only transcript after quiz completion; no corrections or additional material.

---

1. `register_decorator_template` enumerates registrations for one exact, closed `for_each` service key and calls a synchronous factory once for each source that passes `source_filter`. The factory receives frozen `RegistrationInfo` metadata and returns a `DecoratorTemplate` containing the target selector, decorator type, and options. To bind each generated `AlertingAction` to its own channel registration:

```python
def alert_for(source):
    return DecoratorTemplate(
        services=DerivedServices(Action),
        decorator_type=AlertingAction,
        arguments={"channel": select(cf.with_id(source.id))},
    )

builder.register_decorator_template(
    for_each=AlertChannel,
    template=alert_for,
)
```

Here, `source.id` identifies the selected registration. Source enumeration does not activate the source; the page says the source is not instantiated merely to enumerate it. At runtime, the frozen plan resolves dependencies normally. ([Decorator templates](file:///var/folders/s1/8flp14pj3bv3jnzfk7_9n0lr0000gp/T/clean-ioc-m09-reader-r2-9boyg3ca/decorator-templates.md), opening and “One source, one target”; “Ordering, overlap, and lifecycle”)

2. Put the source tag filter on the declaration and the target predicate on the returned definition:

```python
source_filter = cf.has_tag("delivery", "buffered")

def alert_for(source):
    return DecoratorTemplate(
        services=DerivedServices(Action),
        decorator_type=AlertingAction,
        arguments={"channel": select(cf.with_id(source.id))},
        when=cf.has_descendant(cf.has_tag("capability", "alerts")),
    )

builder.register_decorator_template(
    for_each=AlertChannel,
    source_filter=source_filter,
    template=alert_for,
)
```

`source_filter` receives one canonical, parentless source component; it retains its ordinary dependency/build context. `when` receives each prospective target occurrence in its actual undecorated parent context, with its ordinary dependency subtree and descendants available. Both are ordinary one-component filters, evaluated separately at build time; neither receives a combined source-and-target pair. Generated and ordinary decorators are recursively excluded from both views, so dependencies introduced solely by decorators cannot make `when` succeed. ([Decorator templates](file:///var/folders/s1/8flp14pj3bv3jnzfk7_9n0lr0000gp/T/clean-ioc-m09-reader-r2-9boyg3ca/decorator-templates.md, “Two sources and selective targets”; [advanced/filtering.md](file:///var/folders/s1/8flp14pj3bv3jnzfk7_9n0lr0000gp/T/clean-ioc-m09-reader-r2-9boyg3ca/advanced/filtering.md), “Composing filters” and “Decorator selection sees the undecorated core”)

3. An explicit `ServiceGroup` selector includes only registrations whose `groups=` contains that exact group object. Thus of the two `Action` registrations, it selects only the second one that joined the group. It excludes the third registration: implementation inheritance alone does not qualify when its registered service contract is unrelated. `DerivedServices(Action)` selects available registrations whose registered service contract derives from `Action`, so it selects both `Action` registrations regardless of group membership and excludes the unrelated-contract registration. Neither selector creates registrations, adds group memberships, or creates injectable collections; group membership also does not change ordinary service resolution. ([Decorator templates](file:///var/folders/s1/8flp14pj3bv3jnzfk7_9n0lr0000gp/T/clean-ioc-m09-reader-r2-9boyg3ca/decorator-templates.md, “Explicit membership or registered-contract matching”)

4. No. Same-named `ServiceGroup` objects are distinct identities. Define the group once in a shared module and import that same object into both modules. `action_bundle.py` uses it in `groups=[alerted_actions]`; `alert_policy.py` uses it in `DecoratorTemplate(services=alerted_actions, ...)`. `contributes=` keys are for `ProviderMapGroup`, a separate provider-map feature; they are not needed for decorator templates. Group membership does not alter ordinary service resolution. ([Decorator templates](file:///var/folders/s1/8flp14pj3bv3jnzfk7_9n0lr0000gp/T/clean-ioc-m09-reader-r2-9boyg3ca/decorator-templates.md, “Explicit membership or registered-contract matching”; [advanced/special-dependency-types.md](file:///var/folders/s1/8flp14pj3bv3jnzfk7_9n0lr0000gp/T/clean-ioc-m09-reader-r2-9boyg3ca/advanced/special-dependency-types.md), “Explicit provider-map groups”)

5. The discovery rule can pass the shared group when registering generated targets:

```python
builder.register_decorator_template(
    for_each=AlertChannel,
    template=alert_for,
)
builder.register_subclasses(Action, groups=[alerted_actions])
```

Assuming `PublishAction` is a qualifying subclass and is imported before `build()`, discovery materializes its registration before template expansion; the template can then select it. The selector itself does not discover classes. A subclass imported after a successful build does not change the immutable container; a new builder/build is required. ([Decorator templates](file:///var/folders/s1/8flp14pj3bv3jnzfk7_9n0lr0000gp/T/clean-ioc-m09-reader-r2-9boyg3ca/decorator-templates.md, “Explicit membership or registered-contract matching”; “Editing, overlays, and boundaries”; [generics.md](file:///var/folders/s1/8flp14pj3bv3jnzfk7_9n0lr0000gp/T/clean-ioc-m09-reader-r2-9boyg3ca/generics.md), opening discovery discussion)

6. The factory can call `source.implementation_bindings(TransportBackend)` to get a read-only mapping keyed by `TransportBackend`’s actual TypeVar objects, with the binding for `Socket`; it returns `None` if projection is unavailable. This source binding is separate from target generic projection. For each eligible closed target request, the compiler projects the target’s registered service contract onto the `Action` selector contract, then specializes the decorator’s wrapped argument and dependencies using those target bindings. Same-named but distinct TypeVars remain distinct. If `implementation_type` is unavailable for a callable source, the compiler does not guess its implementation binding. The originally requested closed target key, including its alias, is retained. Ambiguous or unresolved target projection fails build with a diagnostic. `for_each=Channel` is not equivalent: `for_each` requires an exact closed source key such as `Channel[Notice]`. ([Decorator templates](file:///var/folders/s1/8flp14pj3bv3jnzfk7_9n0lr0000gp/T/clean-ioc-m09-reader-r2-9boyg3ca/decorator-templates.md, opening; “One source, one target”; “Generic identities and projection”)

7. Define a target predicate that requires a resource descendant with the selected source’s label, then bind the policy dependency to that source by ID:

```python
def policy_for(source):
    return DecoratorTemplate(
        services=DerivedServices(Target),
        decorator_type=ResourceDecorator,
        arguments={"policy": select(cf.with_id(source.id))},
        when=cf.has_descendant(
            cf.has_tag("resource-label", source.name)
        ),
    )
```

This assumes the source’s `name` is the "short" or "long" label; the packet does not define a tag syntax for parameterizing a predicate from a source, though it establishes that filters may use metadata and that `cf.has_tag` and `cf.has_descendant` are composable. If instead the label is in a tag, the factory can inspect source tags, but the exact `RegistrationInfo.tags` representation is not explained. With ordinary descendants included recursively, all three "short" resources—including one nested under a dependency—make the short source’s predicate true; no "long" resource makes the long source’s predicate true. One template adds at most one layer per template/source-registration/target-occurrence combination, so each matching source contributes one layer to this target occurrence. The exact `with_id(source.id)` binding prevents another registration of the same class from substituting; if that registration cannot be injected, normal build diagnostics report the missing exact source dependency rather than choosing a same-class registration. ([Decorator templates](file:///var/folders/s1/8flp14pj3bv3jnzfk7_9n0lr0000gp/T/clean-ioc-m09-reader-r2-9boyg3ca/decorator-templates.md, “Two sources and selective targets”; “Ordering, overlap, and lifecycle”; “Inspection and errors”; [advanced/filtering.md](file:///var/folders/s1/8flp14pj3bv3jnzfk7_9n0lr0000gp/T/clean-ioc-m09-reader-r2-9boyg3ca/advanced/filtering.md), “Composing filters”)

8. Higher positions are further outside. At position 9, `Validate` is outermost. At position 4, equal-position declaration order is outside-to-inside, so `Annotate` is outside `Measure`. The order is:

```text
Validate → Annotate → Measure → core
```

Two distinct templates selecting the same source and target are additive; each template/source/target combination can add a layer. An ordinary dependency added only by `Annotate` cannot make another template’s `when` pass because predicates see the undecorated core subtree. ([decorators.md](file:///var/folders/s1/8flp14pj3bv3jnzfk7_9n0lr0000gp/T/clean-ioc-m09-reader-r2-9boyg3ca/decorators.md), “Ordering”; [decorator-templates.md](file:///var/folders/s1/8flp14pj3bv3jnzfk7_9boyg3ca/decorator-templates.md), “Ordering, overlap, and lifecycle” and “Two sources and selective targets”)

9. At equal position, nearer-overlay source layers are outside inherited layers. Within a layer, earlier source registrations are outside later ones. The nested target’s source-layer order is:

```text
Elm → Cedar → Dahlia → Aster → Birch → target core
```

If Birch alone has position 20, its generated layer takes precedence and is outside all position-5 layers:

```text
Birch → Elm → Cedar → Dahlia → Aster → target core
```

The inherited root singleton keeps its anchored root plan, so overlay sources do not wrap it. A plain child scope reuses its existing plan; an overlay built with `new_scope_builder()` compiles a new plan. A group object alone cannot expose a boundary-private source; boundary visibility still controls which sources the template can use. Filters and factories can execute again for preview queries, overlay builds, or retries after failed builds, and are not called during ordinary resolution. ([Decorator templates](file:///var/folders/s1/8flp14pj3bv3jnzfk7_9n0lr0000gp/T/clean-ioc-m09-reader-r2-9boyg3ca/decorator-templates.md, “Ordering, overlap, and lifecycle”; “Editing, overlays, and boundaries”; [scopes.md](file:///var/folders/s1/8flp14pj3bv3jnzfk7_9n0lr0000gp/T/clean-ioc-m09-reader-r2-9boyg3ca/scopes.md), “ScopeBuilder overlays”; [boundaries.md](file:///var/folders/s1/8flp14pj3bv3jnzfk7_9n0lr0000gp/T/clean-ioc-m09-reader-r2-9boyg3ca/boundaries.md), “Decorators, scope slots, and overlays”)

10. Example using an explicit group:

```python
from clean_ioc import (
    ContainerBuilder,
    DecoratorTemplate,
    ServiceGroup,
    Tag,
    select,
)
from clean_ioc import component_filters as cf


class Notice:
    def __init__(self, text: str):
        self.text = text


class Channel:
    def __init__(self, prefix: str):
        self.prefix = prefix
        self.sent: list[str] = []

    def send(self, notice: Notice) -> str:
        result = f"{self.prefix}:{notice.text}"
        self.sent.append(result)
        return result


class Action:
    def run(self, text: str) -> str:
        return text


class AlertAction(Action):
    def __init__(self, inner: Action, channel: Channel):
        self.inner = inner
        self.channel = channel

    def run(self, text: str) -> str:
        return self.channel.send(Notice(self.inner.run(text)))


actions = ServiceGroup("alert-actions", service_type=Action)
builder = ContainerBuilder()
channel = Channel("buffered")
builder.register(Channel, instance=channel, name="buffered",
                 tags=[Tag("delivery", "buffered")])
builder.register(Action, groups=[actions], tags=[Tag("capability", "alerts")])


def make_alert(source):
    return DecoratorTemplate(
        services=actions,
        decorator_type=AlertAction,
        arguments={"channel": select(cf.with_id(source.id))},
        when=cf.has_tag("capability", "alerts"),
    )


builder.register_decorator_template(
    for_each=Channel,
    source_filter=cf.has_tag("delivery", "buffered"),
    template=make_alert,
)

with builder.build() as container:
    assert container.resolve(Action).run("hello") == "buffered:hello"
    assert channel.sent == ["buffered:hello"]
```

To switch to automatic selection, replace `services=actions` with `services=DerivedServices(Action)` and add `DerivedServices` to the `clean_ioc` imports. Remove `groups=actions` from the `builder.register(Action, ...)` call. The source filter, exact source argument binding, target `when`, and assertions can remain unchanged. The packet does not establish the exact `RegistrationInfo` field types or full static typing accepted for the template factory; this example uses the documented unannotated `source` pattern. ([Decorator templates](file:///var/folders/s1/8flp14pj3bv3jnzfk7_9n0lr0000gp/T/clean-ioc-m09-reader-r2-9boyg3ca/decorator-templates.md, “One source, one target”; “Two sources and selective targets”; “Explicit membership or registered-contract matching”; “Inspection and errors”)
