# Supplied container and scoped slots

Declare a slot for a value that the application creates after compilation.
`ContainerBuilder.build()` compiles its selection and lifetime; `provide()` later
supplies the instance. Clean IoC never enters or finalizes supplied values.

```python
from clean_ioc import ContainerBuilder

class AppConfig:
    pass

class RequestContext:
    pass

class Handler:
    def __init__(self, config: AppConfig, request: RequestContext):
        self.config, self.request = config, request

builder = ContainerBuilder()
builder.declare_slot(AppConfig, target="container")
builder.declare_slot(RequestContext, target="scoped")
builder.register(Handler)
with builder.build() as container:
    config = AppConfig()
    container.provide(AppConfig, config)
    container.check_ready()
    with container.new_scope() as scope:
        request = RequestContext()
        scope.provide(RequestContext, request)
        handler = scope.resolve(Handler)
        assert handler.config is config
        assert handler.request is request
```

`target` is required and must be `"scoped"` or `"container"`. Repeated implicit
slot declarations fail compilation, including redeclarations inherited by a
scope-builder overlay. Declare each input once at its composition owner. An
implicit type/name identity also cannot collide with an explicit binding view;
give both inputs explicit bindings in that case.

| Contract | `target="container"` | `target="scoped"` |
| --- | --- | --- |
| Supply on | The root container | Any supplying scope, including the root |
| Descendants | Share the same instance | Inherit, with local overrides permitted |
| Provision deadline | Before first resolution or warmup anywhere beneath the container | Before the supplying scope's first resolution or warmup |
| Singleton dependency | Valid | `verify()` reports a captive scoped value |
| Ownership | Caller-owned | Caller-owned |

A descendant cannot supply a container input. Supplying a scoped input on the
root keeps its scoped lifetime. Providing the same binding twice on one scope,
providing an undeclared binding, or providing after its deadline raises the
existing provision errors. Closed scopes reject provision and resolution.
A failed readiness check leaves provisions open for repair.

## Selection and stable bindings

`declare_slot()` accepts `name`, `tags`, `binding`, and `when`. Names and tags use
the ordinary component filters. A binding is a nonempty application-defined string
that identifies one input independently of registration IDs or graph occurrences.
Aliases normalize to the same canonical service type. Compiled Components expose
`slot_binding` for inspection, alongside their name, tags, lifetime and supplied
ownership; reports never include the supplied instance.

**Every conditional slot requires an explicit binding.** `when` runs against the
slot Component during compilation. Use `cf.parent(...)` to select its immediate
consumer. Provider and collection wrappers are real parents; there is no implicit
ancestor search.

```python
from clean_ioc import ContainerBuilder, Tag
from clean_ioc import component_filters as cf
from clean_ioc.arguments import select

class Client:
    pass

class Payments:
    def __init__(self, client: Client):
        self.client = client

class Refunds:
    def __init__(self, client: Client):
        self.client = client

builder = ContainerBuilder()
for consumer, binding in ((Payments, "payments.client"), (Refunds, "refunds.client")):
    builder.declare_slot(
        Client, target="container", name="primary", tags=[Tag("external")],
        binding=binding, when=cf.parent(cf.service_type_is(consumer)),
    )
    builder.register(consumer, arguments={"client": select(cf.has_tag("external"))})
with builder.build() as container:
    payments, refunds = Client(), Client()
    container.provide(Client, payments, binding="payments.client")
    container.provide(Client, refunds, binding="refunds.client")
    assert container.resolve(Payments).client is payments
    assert container.resolve(Refunds).client is refunds
```

Different bindings do not break selection ties. Every compiled scalar dependency
must select one binding; competing eligible bindings fail `build()` and `verify()`
with `ambiguous-slot`, identifying the consumer, argument and declaration origins.
Later scope-builder compilation checks its new contexts. Resolution executes the
frozen lookup and does not rerun `when`.

Distinct named, tagged or conditional views may intentionally share an explicit
binding. Their canonical type and lifetime must agree. A scalar lookup matching
several views of that binding receives the same value; a collection or provider
map includes the binding once, using the first matching view's metadata. An
identical unconditional view declared twice is an error. Callback identities are
never compared to decide whether conditional views overlap.

`provide(T, value, name=...)` considers all declarations for that type/name,
including conditional declarations. It succeeds only when they identify one
binding. Otherwise specify `binding=...`; that form validates the type and uses
the binding independently of its view names. Provision never executes `when`.
`has_slot()` and `has_provision()` also accept `binding=`; an ambiguous
`has_provision()` lookup requires the explicit binding.

## Registrations, collections and deferred targets

Ordinary registrations, including existing fallback registrations, take precedence.
Slots fill the remaining selection hole. Collections use matching slots only when
no registrations match. This extends the former scoped-slot behaviour: an
unnamed slot can now appear in an otherwise empty collection. Matching views of
one binding contribute one member. Registration collection cardinality is unchanged.

Slots can be resolved as roots and filtered by their names/tags. Conditional root
eligibility is evaluated with no parent. Provider root targets are selected in
their provider context, and provider collection members in their collection
context. As with other root filters, an application may pass a filter at runtime;
if it matches competing slot bindings, resolution raises `ScopeProvisionError`.

Constructors, decorators and pre-configurations can consume slots. Injected
`Provider[T]`, `AsyncProvider[T]`, managed providers, and their collection targets
freeze the selected input bindings. Callback-based provider maps also use slots
as fallback targets and keep the provider wrapper as each slot's parent.
Contribution-group maps select registered contributors; slots do not declare
contributions. Default root collections of provider handles retain the existing
explicit-filter requirement; use an explicit filter such as `all_components`
when selecting those handles.

## Required inputs and activation

`check_ready()` checks all required container bindings together without activating
anything or sealing provisions. Ordinary resolution and named warmup perform the
same check before their first activation. Scoped values are checked when used;
readiness never demands values for future request scopes.

```python
from clean_ioc import ContainerBuilder, Provider, ScopeProvisionError

class Client:
    pass

class Service:
    def __init__(self, client: Provider[Client]):
        self.client = client

builder = ContainerBuilder()
builder.declare_slot(Client, target="container", binding="external.client")
builder.register(Service)
with builder.build() as container:
    try:
        container.check_ready()
    except ScopeProvisionError as error:
        assert "external.client" in str(error)
    client = Client()
    container.provide(Client, client, binding="external.client")
    container.check_ready()
    assert container.resolve(Service).client() is client
```

Required inputs are selected container bindings reachable from frozen public roots,
provider roots (including deferred targets), and declared warmup targets.
Unconditional slot declarations expose public roots and therefore require inputs.
A conditional declaration with no executable occurrence is optional. Changing the
declared provider surface can remove unused deferred targets. Internal managed
adapters contribute requirements only when a reachable managed ResolutionContext
can activate their frozen targets. Private,
architecture-only boundary roots do not introduce required runtime inputs.
There is no optional `WarmupTarget` API: every compiled startup target contributes
its selected dependencies even if the application never invokes that warmup.
These checks inspect frozen data and never replay application callbacks.

After the first successful activation preflight, all container inputs are sealed,
including previously optional inputs. `new_scope()` itself performs no readiness
traversal and does not seal inputs. Supplied values stay outside cleanup ownership.

## Overlays and boundaries

`ScopeBuilder` overlays can add scoped inputs and consume inherited container
inputs. They cannot declare new container inputs, before or after ancestor
activation; declare those on the root `ContainerBuilder`. An overlay that introduces
a new dependency on an unprovided, already sealed container input fails clearly
with `overlay-missing-container-slot`.

Boundaries can import an unconditional root slot with `Use.root(T, filter=...)`.
Conditional root-slot imports fail with `boundary-conditional-slot-unsupported`;
private boundary slots remain unsupported. Use an unconditional shared input or
keep conditional consumers in the root composition.

The feature works through ordinary build/provide/resolve paths. Persistence and
loading of compiled artifacts are separate features.
