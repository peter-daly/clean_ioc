# Fresh reader round 1 — verbatim Phase B

Agent `/root/m09_reader_r1`, gpt-6-luna low, same reader and public packet as Phase A. No coaching or corrected docs supplied. Reader final response follows.

---

1. The factory receives a frozen `RegistrationInfo` for each source registration that passes `source_filter`. It includes `id`, `service_type`, `implementation_type`, `name`, and `tags`. It returns a `DecoratorTemplate` containing the decorator type, target selector, and ordinary decorator options. Bind each decorator’s sink argument to that specific registration with `select(cf.with_id(source.id))`. The source is not instantiated just to enumerate it. [Decorator templates, “One source, one target” and “Two sources and selective targets”]

```python
def measured_for(source):
    return DecoratorTemplate(
        services=DerivedServices(Job),
        decorator_type=MeasuredJob,
        arguments={"sink": select(cf.with_id(source.id))},
    )
```

2. Put the remote-sink restriction in `source_filter` and the telemetry-dependent target restriction in the returned template’s `when`:

```python
source_filter=cf.has_tag("location", "remote")
# inside the returned DecoratorTemplate:
when=cf.has_descendant(cf.has_tag("needs", "telemetry"))
```

`source_filter` sees a canonical source `Component` with no parent and its ordinary dependency/build context; ordinary and generated decorators are excluded. `when` sees each prospective target occurrence in its actual, undecorated parent context, with its ordinary dependency subtree, including descendants. Decorators and dependencies introduced only by decorators are excluded from both views. The filters are evaluated separately; neither receives both a source and target. [Decorator templates, “Two sources and selective targets”; component filtering, “Component model,” “Decorator selection sees the undecorated core,” and “Composing filters”]

3. The `ServiceGroup` selects only registrations that both have a compatible registered service contract and explicitly join that exact group object through `groups=[group]`. Of the two `Job` registrations, only the member is selected. `DerivedServices(Job)` selects available registrations whose **registered service contract** derives from `Job`, whether or not they joined a group. A class inheriting `Job` but registered under an unrelated service contract is not selected by that rule. `DerivedServices` creates no registrations, memberships, map keys, injectable collections, or provider-map groups. [Decorator templates, “Explicit membership or registered-contract matching”]

4. Two independently constructed `ServiceGroup("measured", service_type=Job)` objects are different identities, so the policy group will not select the registration bundle’s members. Declare one group in a shared module and import that same object in both bundles:

```python
# shared.py
measured_jobs = ServiceGroup("measured", service_type=Job)

# registration bundle
builder.register(Job, SomeJob, groups=[measured_jobs])

# policy bundle
DecoratorTemplate(services=measured_jobs, ...)
```

No contribution keys are needed; those belong to the separate `ProviderMapGroup` feature. Application code cannot resolve services “from the group”: group membership only selects decorator targets and does not alter ordinary resolution or provide an injectable runtime group or map. [Decorator templates, “Explicit membership or registered-contract matching” and “Editing, overlays, and boundaries”; special dependency types, “Explicit provider-map groups”]

5. Queue subclass discovery before `build()`, passing the group so materialized registrations inherit membership:

```python
builder.register_subclasses(Job, groups=[measured_jobs])
```

The documentation says `groups=` is available on `register_subclasses`, `register_generic_subclasses`, and `register_pattern`. Discovery registrations materialize before template expansion, so declaration order relative to the template does not prevent the template from seeing them. If imports need to happen first, the page says to use `ensure_import_modules=`. A target selector does not discover classes itself. After a successful build, the plan is immutable; a newly available subclass needs a new builder/build. [Decorator templates, “Explicit membership or registered-contract matching” and “Target declarations”; generics, “Filtering discovered subclasses”]

6. The factory can inspect `source.service_type` and, when the implementation type is statically known, call `source.implementation_bindings(ArchiveBackend)`. That returns a read-only mapping keyed by `ArchiveBackend`’s actual `TypeVar` objects, or `None` if projection is unavailable; unknown implementation metadata is not guessed. Separately, for each eligible closed target request, the compiler projects the target’s **registered service contract** onto the `ServiceGroup` or `DerivedServices` contract and specializes the wrapped argument and dependencies from those target bindings. Source, target, and decorator retain distinct TypeVar identities, even when the variables share a name. Resolution preserves the originally requested target key, including a closed alias or implementation lookup key. Ambiguous or unresolved target projection fails build with a diagnostic rather than choosing a mapping. [Decorator templates, “Generic identities and projection”]

7. Give each source registration stable identifying metadata, then bind the decorator’s dependency to that registration ID:

```python
arguments={"backend": select(cf.with_id(source.id))}
```

The factory can use source metadata to construct a source-specific `when`, for example a descendant filter keyed to the source ID or a name/tag that identifies “cold” versus “hot.” `when` only sees the target occurrence and its ordinary dependency subtree; it cannot jointly inspect source and target. If the target reaches the cold registration through three paths, the compiler adds at most one layer for that template/source/target-occurrence combination. It adds no hot-source layer if the source-specific target filter does not match. If a selected exact source cannot satisfy the dependency at the injection point, compilation reports a missing exact source dependency; it does not substitute another registration with the same service or implementation class. [Decorator templates, “One source, one target,” “Two sources and selective targets,” “Ordering, overlap, and lifecycle,” and “Inspection and errors”]

8. Higher `position` values are outside; equal positions retain earlier registration order from outside to inside. The order is therefore:

```text
OuterTrace(Timing(Checksum(core)))
```

Two distinct templates are additive even when they choose the same source and target, with at most one layer per template/source/target-occurrence combination. A dependency introduced only by one decorator cannot make another template’s `when` match, because target predicates inspect the undecorated core subtree. [Decorator templates, “Ordering, overlap, and lifecycle” and “Two sources and selective targets”; decorators, “Ordering”; component filtering, “Decorator selection sees the undecorated core”]

9. A plain `new_scope()` reuses the existing plan, so it cannot acquire new template layers. An overlay built through `new_scope_builder()` compiles a new plan: newly visible source registrations can add layers to overlay-owned target plans, and new eligible targets can receive inherited template layers. An inherited parent singleton remains anchored to the parent activation plan and cannot be rewired by the overlay. A shared group object does not expose private boundary registrations; template and source visibility still follows boundary rules and explicit exposures/uses. Filters and factories may run again for a preview query, overlay build, or retry after a failed build, but not during ordinary resolution. [Decorator templates, “Editing, overlays, and boundaries” and “Ordering, overlap, and lifecycle”; scopes, “ScopeBuilder overlays”; boundaries, “Decorators, scope slots, and overlays”]

10. This complete program follows the packet’s explicit-membership example pattern. It uses two remote sinks to show that each selected source gets an exact binding; the local sink is filtered out.

```python
from clean_ioc import ContainerBuilder, DecoratorTemplate, ServiceGroup, Tag, select
from clean_ioc import component_filters as cf


class TelemetrySink:
    def __init__(self, label, events):
        self.label = label
        self.events = events

    def record(self, value):
        self.events.append(f"{self.label}:{value}")


class Job:
    def run(self, value):
        return value.upper()


class BasicJob(Job):
    pass


class MeasuredJob(Job):
    def __init__(self, inner: Job, sink: TelemetrySink):
        self.inner = inner
        self.sink = sink

    def run(self, value):
        self.sink.record(value)
        return self.inner.run(value)


measured_jobs = ServiceGroup("measured", service_type=Job)
events = []
builder = ContainerBuilder()

builder.register(
    TelemetrySink,
    instance=TelemetrySink("first", events),
    tags=[Tag("location", "remote")],
)
builder.register(
    TelemetrySink,
    instance=TelemetrySink("second", events),
    tags=[Tag("location", "remote")],
)
builder.register(
    TelemetrySink,
    instance=TelemetrySink("local", events),
    tags=[Tag("location", "local")],
)
builder.register(Job, BasicJob, groups=[measured_jobs], tags=[Tag("needs", "telemetry")])


def measured_for(source):
    return DecoratorTemplate(
        services=measured_jobs,
        decorator_type=MeasuredJob,
        arguments={"sink": select(cf.with_id(source.id))},
        when=cf.has_tag("needs", "telemetry"),
    )


builder.register_decorator_template(
    for_each=TelemetrySink,
    source_filter=cf.has_tag("location", "remote"),
    template=measured_for,
)

with builder.build() as container:
    assert container.resolve(Job).run("hello") == "HELLO"
    assert events == ["first:hello", "second:hello"]
```

To use automatic target selection, replace `services=measured_jobs` with `services=DerivedServices(Job)` and remove `groups=[measured_jobs]` from the `Job` registration. The source filter, exact source binding, and target `when` remain unchanged. The packet demonstrates the syntax used above, but it does not provide full API signatures or parameter types/defaults for `DecoratorTemplate` and `register_decorator_template()`. [Decorator templates, “One source, one target,” “Two sources and selective targets,” and “Explicit membership or registered-contract matching”]
