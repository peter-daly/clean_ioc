# Component filtering

Clean IoC 2 uses one immutable `Component` model and one filter vocabulary everywhere.

```python
import clean_ioc.component_filters as cf
from clean_ioc import Component, ContainerBuilder, Tag, select
```

A component occurrence exposes:

- stable registration `id` and occurrence-specific `occurrence_id`;
- `service_type`, `implementation`, and normalized `implementation_type`;
- `lifespan`, `name`, `tags`, `kind`, `activation`, and incoming `argument`;
- activation properties including `requires_async` and `manages_cleanup`;
- decorator `position` when the occurrence is a decorator;
- `generic_mapping` and immutable `build_args`;
- read-only `parent`, `dependencies`, `decorators`, `decorated`, and `pre_configurations`;
- static descendant queries.

`Component` does not expose a runtime `instance` or `instance_type`. Composition, dependency, decorator, and
pre-configuration filters are evaluated at build time and their decisions are frozen. A filter passed directly to
`resolve(...)` selects among the already-compiled roots at runtime; it cannot alter their dependency plans.

## Root selection

```python
builder = ContainerBuilder()
builder.register(str, instance="development", name="dev")
builder.register(str, instance="production", tags=[Tag("env", "prod")])
container = builder.build()

assert container.resolve(str, filter=cf.with_name("dev")) == "development"
assert container.resolve(str, filter=cf.has_tag("env", "prod")) == "production"
```

Omitting `filter` selects unnamed components. An explicit filter **replaces** that default; it is not ANDed with
an unnamed restriction. Thus `resolve(str, filter=cf.with_name("dev"))` can select the named registration above.

Root resolution takes the first matching compiled candidate. Within the same registration layer and definition tier,
candidates are considered in reverse registration order (LIFO): if unnamed A is registered before unnamed B,
`resolve(Service)` selects B. Existing layer, visibility and generic-definition rules still determine the candidate
set and order. Root selection does not apply `parent_precedence` or registration preference chains. Its runtime filter
chooses a root plan; dependencies already frozen into that plan keep their original selections.
`resolve` and `resolve_async` accept a `filter` argument, but have no `prefer` keyword.

## Dependency selection

```python
class Client:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint


builder = ContainerBuilder()
builder.register(str, instance="https://api.example", name="api")
builder.register(
    Client,
    arguments={"endpoint": select(cf.with_name("api"))},
)
container = builder.build()
```

The same default rule applies to dependency arguments: `select()` uses the unnamed filter, while an explicit filter
replaces it. `select(cf.has_tag("hosted"))`, for example, admits named and unnamed candidates with that tag.

For collection arguments, the predicate selects every matching component and preserves candidate order. Within the same
registration layer and definition tier, registering A then B produces `[B, A]` in a `list[Service]` when both match.
Parent precedence and preferences do not change that membership or order. Unordered collection types retain their own
ordering semantics.

### Single dependency selection order

For an injected single dependency, selection proceeds in this order:

1. Apply service-type, generic-definition and visibility rules; compile and validate candidate graphs.
2. Keep candidates accepted by their registration `when` and the consumer's `select` filter.
3. Keep those with the highest effective `parent_precedence` (default `0`).
4. Narrow any remaining tie using the consumer's `select(..., prefer=chain)`.
5. Narrow any remaining tie using each candidate's registration `prefer=chain`.
6. If still tied, an ordinary dependency takes the first remaining candidate (LIFO within a layer/tier) and warns.
   Injected `Provider[T]` and `AsyncProvider[T]` instead require a unique final winner and report an ambiguity error.

A later phase cannot restore an excluded candidate. Preference callbacks are skipped once at most one candidate
remains. See [ordered soft preferences](#ordered-soft-preferences) for the stage-by-stage narrowing rules.

## Contextual registration with `when=`

`when` decides whether a registered component is eligible for one static occurrence. In `Worker → Policy`, both a
registration's `when` predicate and Worker's dependency filter receive the candidate **Policy** component. Use
`cf.parent(...)` to inspect Worker. A matching `when` grants eligibility without adding priority.
Parent-aware rules are explicit:

```python
class SqlConnection:
    pass


class DocumentConnection:
    pass


builder.register(
    Connection,
    SqlConnection,
    when=cf.parent(cf.has_tag("database", "sql")),
)
builder.register(
    Connection,
    DocumentConnection,
    when=cf.parent(cf.has_tag("database", "document")),
)
```

The compiler builds occurrence-specific plans, so the same registration can make different decisions under different generic parents.

## Decorator selection sees the undecorated core

```python
builder.register_decorator(
    Handler,
    TransactionDecorator,
    when=cf.has_descendant(cf.service_type_is(SqlConnection)),
)
```

All decorator predicates are evaluated against the completed undecorated component subtree. Dependencies introduced by one decorator cannot accidentally cause another decorator to become eligible.

The same `when=` argument is available on `pre_configure(...)`. [Decorator templates](../decorator-templates.md) also use `source_filter=` on a canonical, parentless, recursively undecorated source and `when=` on each recursively undecorated target occurrence in its actual parent context.

## Composing filters

Built-in predicates are composable through `funcie`:

```python
production_stripe = cf.has_tag("env", "prod") & cf.with_name("stripe")
not_singleton = ~cf.has_lifespan("singleton")
```

Useful helpers include:

- `with_name`, `with_id`, `name_starts_with`, `name_ends_with`;
- `is_named` (name is not `None`), `is_not_named` (name is `None`, equivalent to `with_name(None)`);
- `implementation_is`, `implementation_type_is`, `implementation_matches_type_filter`;
- `service_type_is`;
- `has_tag`, `has_generic_arg`;
- `has_lifespan`, `has_lifespan_in`;
- `has_build_arg`, `build_arg_is`;
- `parent`, `has_descendant`.

Use `create_filter(callable)` for a custom composable predicate.

### Selector configuration

`ComponentSelector` is a small dataclass for storing filter inputs, for example
as configuration passed to a bundle:

```python
from clean_ioc import ComponentSelector, Tag

selector = ComponentSelector[str](
    service_type=str,
    implementation_type=str,
    name="primary",
    lifespan="singleton",
    tags=[Tag("env", "prod"), Tag("enabled")],
)
component_filter = selector.to_filter()
```

`ComponentSelector[T]` constrains both `service_type` and `implementation_type`
to types compatible with `T` during static type checking. Implementations may be
subclasses of the selected service contract. The generic argument itself adds no
runtime filtering; supply `service_type` or `implementation_type` when needed.
Existing unparameterized selectors remain supported.

Pass the resulting filter anywhere a component filter is accepted, including
`select(...)`, `when=`, or a builder query. All supplied fields and all tags
must match. Service and implementation types use the same normalized comparisons as
`service_type_is` and `implementation_type_is`, respectively. A tag without a value matches any value for that tag
name, and extra component tags are allowed.

All fields default to `Undefined`, available as `from clean_ioc import Undefined`.
`ComponentSelector.default()` creates a selector with every field undefined,
equivalent to `ComponentSelector()`. Use it for parameter defaults such as
`endpoint: ComponentSelector[str] = ComponentSelector[str].default()`.
When every field is `Undefined`, `to_filter()` returns `default_component_filter`,
which selects only unnamed components. Otherwise, undefined fields impose no
restriction and the supplied fields determine the matches. For example,
`ComponentSelector(service_type=str)` includes named string components, while
`ComponentSelector(service_type=str, name=None)` selects only unnamed ones.
Use `ComponentSelector.all()` to match both named and unnamed components, for
example when selecting every hosted service. It supplies `all_components` as its
predicate. An explicitly supplied empty tag iterable also counts as a supplied
field, so `ComponentSelector(tags=[])` continues to match all components. `.all()` and `tags=[]` produce the same
unrestricted eligibility; `.all()` states that intention directly. Explicit
`None` values for service or implementation types are compared by the corresponding
type filter; they do not disable filtering. Supplied lifespans must be valid
lifespans, and supplied tags must be an iterable (use `[]` for no tag restrictions).
The selector is immutable and copies supplied tags into a tuple, so it can safely
be reused by bundles. Existing callers using `None` to omit a field should omit
that argument or pass `Undefined` instead.

### Reading the service type

`selector.resolved_service_type` returns the explicitly configured `service_type` when supplied. Otherwise, it uses
typetoolbox to recover the selector's generic argument. This property does not change the filter produced by `to_filter()`:

```python
from clean_ioc import ComponentSelector, Undefined, default_component_filter

selector = ComponentSelector[str]()
assert selector.resolved_service_type is str
assert selector.service_type is Undefined
assert selector.to_filter() is default_component_filter

assert ComponentSelector[object](service_type=str).resolved_service_type is str
assert ComponentSelector[str].default().resolved_service_type is str
assert ComponentSelector[str].all().resolved_service_type is str
assert ComponentSelector[list[str]]().resolved_service_type == list[str]
assert ComponentSelector[str](service_type=None).resolved_service_type is None
assert ComponentSelector().resolved_service_type is Undefined
```

An explicit `None` is a supplied value and takes precedence over the generic argument. An unparameterized selector,
or one whose service binding is still a bare unresolved type variable, returns `Undefined`. `implementation_type` is
not used as a fallback. A variable annotation alone cannot supply runtime metadata: instantiate `ComponentSelector[str]()`
to retain `str`, rather than assigning `ComponentSelector()` to a variable annotated `ComponentSelector[str]`.

Bindings are retained through `.default()`, `.all()`, specialized subclasses, shallow/deep copies and pickle round trips.
The selector stays immutable, and equality/hash still compare its filter fields. A bundle that uses the resolved type
to choose a service should include that type in its own configuration identity.

### Custom selector predicates

Use `predicate=` to carry an existing `ComponentFilter`, including descendant
conditions and composed filters, through a selector-based bundle API:

```python
from clean_ioc import ComponentSelector, Tag
from clean_ioc import component_filters as cf

selector = ComponentSelector(
    tags=[Tag("hosted")],
    predicate=cf.has_descendant(cf.has_tag("transaction", "main")),
)
component_filter = selector.to_filter()
```

The candidate must have its own `hosted` tag and a descendant tagged with
`transaction=main`. The supplied predicate is ANDed with all supplied metadata
constraints, after those constraints match. A predicate alone does not impose an
unnamed-component restriction; use `name=None` to add that restriction explicitly.
Predicates may be plain callables or existing filters composed with `&`, `|`, and
`~`. Omit the predicate or pass `Undefined` for no custom condition; `None` is not
a valid predicate.

The callback receives a `Component` and runs when the resulting filter is
evaluated, with the same graph view as a raw filter at that call site. Creating a
selector or calling `to_filter()` does not evaluate it. The generic argument does
not statically validate callback logic. The selector retains the callable; it does
not freeze any state captured by that callable.

Bundles with automatic applicability rules should keep those rules separate from
selector defaults. For example, an omitted UoW applicability override can retain
its automatic descendant rule, while an explicit selector replaces that rule.
Mandatory opt-out checks can still be combined with the resulting filter. Neither
`.default()` (unnamed) nor `.all()` (unrestricted) means automatic applicability.

### Selector identity in bundles

Selector equality includes the predicate field, using the callable's own equality
semantics. Ordinary functions compare by identity; separately created closures
are not treated as equivalent policies. Arbitrary callables may be unhashable or
unserializable, and Clean IoC does not derive a stable semantic fingerprint for
them.

Bundle identifiers must account for all policy inputs, including predicates and
applicability overrides. Do not fingerprint only the metadata fields or use a
callback's name, source text, or `repr()` as a stable identity. Use explicit policy
identifiers when stable identity matters, or object identity when only in-process
identity is needed. Bundles should explicitly decide whether different policies
may coexist or constitute conflicting configuration; merely assigning different
keys may install overlapping decorators.

### Implementation filters

`implementation_is(T)` compares `T` with the component's raw implementation. For a factory registration, that is the
factory callable. `implementation_type_is(T)` compares the normalized implementation type, including a factory's
annotated return type:

```python
def create_client() -> Client:
    return Client()


builder.register(Client, factory=create_client)

factory = cf.implementation_is(create_client)
produces_client = cf.implementation_type_is(Client)
```

Custom filters can inspect the same metadata:

```python
async_resource = cf.create_filter(
    lambda component: component.requires_async and component.manages_cleanup,
)
```

Build arguments provide explicit inputs for composition-time filtering:

```python
production = cf.build_arg_is("environment", "production")
has_region = cf.has_build_arg("region")

builder.register(
    PaymentGateway,
    ProductionGateway,
    when=production & has_region,
)
container = builder.build(
    build_args={"environment": "production", "region": "eu-west"},
)
```

Missing keys do not match either helper. Custom filters can read `component.build_args` directly. Pass `build_args=` to
builder preview queries when their temporary compilation should use the same composition inputs as the final build.

## Component IDs and patching

Builder queries use component terminology:

```python
component_id = builder.get_component_id(Service, filter=cf.with_name("primary"))
component_ids = builder.get_component_ids(Service)
exists = builder.has_component(Service, build_args={"environment": "production"})

if component_id is not None:
    builder.patch_component(Service, component_id, lifespan="singleton")
```

Queries and patches must happen before a successful `build()`.

## Parent precedence for overlapping registrations

`when` controls eligibility. A registration can also declare `parent_precedence` to choose between eligible
registrations for an injected single dependency. Higher integers win; the default is zero, including registrations
with a `when` predicate. Independent bundles can therefore agree on contextual overrides without depending on their
installation order:

```python
from clean_ioc import ContainerBuilder
from clean_ioc import component_filters as cf


class WaitPolicy:
    pass


class OrdersWait(WaitPolicy):
    pass


class DefaultWait(WaitPolicy):
    pass


class Worker:
    def __init__(self, policy: WaitPolicy):
        self.policy = policy


builder = ContainerBuilder()
builder.register(WaitPolicy, OrdersWait, when=cf.parent(cf.with_name("orders")), parent_precedence=10)
builder.register(WaitPolicy, DefaultWait)
builder.register(Worker, name="orders")
builder.register(Worker, name="invoices")
with builder.build() as container:
    assert isinstance(container.resolve(Worker, filter=cf.with_name("orders")).policy, OrdersWait)
    assert isinstance(container.resolve(Worker, filter=cf.with_name("invoices")).policy, DefaultWait)
    assert isinstance(container.resolve(WaitPolicy), DefaultWait)
```

Values are signed Python integers, with no reserved ranges or maximum; booleans, floats, strings, `None`, and callbacks
are rejected before registration changes. Negative values can express a low-priority fallback. Consumer filters remain
hard requirements. Equivalent predicates, including repeated conditions, do not create extra weight.

Without preference chains, equal maxima keep registration order: ordinary dependencies choose the latest registration
and warn about ambiguity; `Provider[T]` and `AsyncProvider[T]` require a unique maximum and reject tied maxima. Every candidate is still compiled
and validated, so low precedence cannot hide an invalid dependency or throwing predicate.

An application that intentionally replaces a library policy with precedence `10` can register its replacement with
`parent_precedence=30`. With all values omitted, the later application registration still wins as before. A later zero
cannot override an explicit `10`. Bundle authors should document nonzero policies so their applications can coordinate
these values; there are no universal library, application, geography, or privacy bands. Controlled registration order,
explicit consumer selection, and mutually exclusive `when` rules remain useful alternatives.

The keyword is also available on `register_pattern`, `register_subclasses`, and `register_fallback`, including
discovery fallbacks, boundary builders, and scope builders. Locally owned registrations can be changed before build with
`patch_component(Service, component_id, parent_precedence=20)`; `0` resets the value and `None` leaves it unchanged.

Precedence applies during compilation to single constructor, factory, decorator, and pre-configuration dependencies
and injected typed-provider targets. It does not reorder or trim collections or provider maps, resolve duplicate map
keys, change boundary import/export cardinality, or influence roots, root entrypoints, builder previews, or declared
factory resolution requests. Exact/pattern/open-generic definition selection and boundary visibility run first.
A parent hidden at a boundary makes the declared precedence inapplicable. For comparison with other eligible
candidates, that registration contributes the neutral value **0**: it ties a local `0`, beats a local `-1`, and loses
to a local `1`, regardless of its declared value. Its registration preference chain is skipped entirely.

`cf.parent` still observes the immediate parent. In `Worker → Provider[WaitPolicy] → WaitPolicy`, the immediate parent
is the provider; use `cf.parent(cf.parent(cf.with_name("orders")))` when that is the intended path. Collections also
introduce their own parent node. Values are never inherited by children or added across edges. Activation uses the
frozen choice without replaying predicates; a new scope overlay can compile new choices, while existing singleton
plans remain anchored to their original dependencies.

## Ordered soft preferences

Use `prefer(predicate).then(predicate)` when a characteristic is desirable but a fallback must remain valid.
`when` and `select(filter)` still determine eligibility. A preference only breaks a remaining tie; an all-false stage
keeps every survivor. Earlier stages cannot be outweighed by later stages.

Each stage operates on the candidates **entering that stage**:

1. If fewer than two remain, stop without invoking a callback.
2. Evaluate the stage once for every remaining candidate, in candidate order. Count false results as evaluations too;
   finding a true result does not stop the stage.
3. If at least one result is true, retain all true candidates. If all results are false, retain the entire incoming set.
4. Continue with only those survivors. An eliminated candidate is never evaluated at a later stage.

For a consumer chain, the algorithm is:

```text
remaining = eligible candidates tied at maximum precedence
for each predicate in the consumer chain:
    if remaining contains fewer than two candidates: stop
    results = call the predicate for EVERY candidate in remaining
    matches = candidates whose recorded result is true
    if matches is nonempty: remaining = matches
    otherwise: leave remaining unchanged
```

The callback count is the number entering a reached consumer stage, **not** the number matching it. Determine results
before narrowing. For example, with two incoming candidates X and Y, a stage that selects only X still makes two calls
(one true and one false). Only the *next* stage is skipped. A chain never sorts or reverses survivors.

For example, register A (primary/US), B (primary/EU), then C (secondary/EU) in one layer. The consumer chain
`prefer(primary).then(EU)` makes these decisions:

| Stage | Candidates evaluated, in order | True results | Survivors | Callback calls |
| --- | --- | --- | --- | ---: |
| `primary` | C, B, A | B, A | B, A | 3 |
| `EU` | B, A | B | B | 2 |

B wins after **five** callbacks. C is not evaluated at stage two. If the first predicate instead returns false for
all three candidates, all three reach the EU stage: that variant makes **six** callbacks and leaves C and B tied.
An ordinary dependency then selects C (the later registration) and warns; an injected typed provider reports ambiguity.

```python
from clean_ioc import ContainerBuilder, Tag, prefer, select
from clean_ioc import component_filters as cf


class Endpoint:
    pass


class Europe(Endpoint):
    pass


class America(Endpoint):
    pass


class Client:
    def __init__(self, endpoint: Endpoint):
        self.endpoint = endpoint


preferred_endpoint = prefer(cf.has_tag("primary")).then(cf.has_tag("region", "eu"))
builder = ContainerBuilder()
builder.register(Endpoint, Europe, tags=[Tag("primary"), Tag("region", "eu")])
builder.register(Endpoint, America, tags=[Tag("primary"), Tag("region", "us")])
builder.register(Client, arguments={"endpoint": select(cf.all_components, prefer=preferred_endpoint)})
with builder.build() as container:
    assert isinstance(container.resolve(Client).endpoint, Europe)
```

Both endpoints satisfy the first stage, so both survive to the region stage. If neither were primary, the region
stage would still select Europe. If only America were primary, America would win immediately: later region or name
matches cannot outweigh the first stage. `ComponentPreference` holds an immutable tuple of predicates; `.then(...)`
returns a new chain, so extending a shared chain does not modify existing consumers.

`select(prefer=chain)` retains the usual **unnamed** eligibility filter. A name preference cannot revive excluded named
registrations. Use `select(cf.all_components, prefer=chain)` to admit both named and unnamed candidates. Boolean
composition inside a stage, such as `cf.has_tag("primary") & cf.has_tag("region", "eu")`, keeps its normal short-circuit
semantics. It gains no extra weight. An ID predicate is just another stage, without special priority.

Registrations can also have their own chain. Each predicate receives the candidate component, with the same
source metadata and parent visibility as `when`; navigate explicitly with `cf.parent(...)`:

```python
builder = ContainerBuilder()
builder.register(
    Endpoint,
    Europe,
    prefer=prefer(cf.parent(cf.has_tag("region", "eu"))),
)
builder.register(
    Endpoint,
    America,
    prefer=prefer(cf.parent(cf.has_tag("region", "us"))),
)
builder.register(Client, tags=[Tag("region", "eu")])
with builder.build() as container:
    assert isinstance(container.resolve(Client).endpoint, Europe)
```

The [selection order](#single-dependency-selection-order) applies the consumer chain before registration chains.
A consumer stage uses the same predicate for each survivor. A registration stage instead uses each survivor's own
predicate at that position. A missing rule supplies a neutral false result without a callback. It removes a candidate
only when another survivor returns true at that stage. A longer chain has no inherent advantage:

| A's registration chain | B's registration chain | Result |
| --- | --- | --- |
| `[false, true]` | `[false]` | Both return false at stage one, so both survive. A alone returns true at stage two and wins. |
| `[true]` | `[false, true, true]` | A wins at stage one; B's later predicates never run. |
| `[false]` | No chain | Both contribute false at stage one, so they remain tied. Ordinary LIFO or provider ambiguity applies. |

The bracketed values illustrate callback results; callers supply predicates rather than boolean lists.
An all-false stage preserves fallback candidates; it does not mean they matched that predicate.
For registration-stage callback counts, count only surviving candidates that actually have an applicable predicate
at that position. A candidate with no chain contributes zero calls at **every** stage, including the first. For example,
`[false, false]` against an absent chain makes one call at each of two stages (two total), then remains tied.

For a conflict example, if Europe has a registration preference that matches its parent but the consumer explicitly
prefers America, America wins at equal numeric precedence. Giving Europe `parent_precedence=10` and America `0`
selects Europe before either chain runs. Library authors should document registration preferences: even one true
stage can defeat an application's later zero-precedence fallback. Applications can deliberately override this with
a consumer preference, a hard filter, or a higher numeric precedence.

`prefer=` is available on `register`, `register_pattern`, `register_subclasses`, and `register_fallback`,
including boundary and scope builders. `patch_component(..., prefer=Undefined)` leaves the chain unchanged,
`prefer=None` clears it, and a new chain replaces it. Patches are local and available before successful build.
`ComponentSelector` remains an eligibility abstraction; pair `selector.to_filter()` with a separate chain.

Preferences apply only to single injected dependencies, including factory, decorator, pre-configuration, and typed
provider target dependencies. They do not change roots, runtime explicit filters, declared `ResolutionContext`
requests, `use_component`, previews, scope slots, boundary `Use`/`Expose` cardinality, or provider-map membership/keys.
Duplicate [provider-map keys](special-dependency-types.md#lazy-provider-maps) still fail build, and an ambiguous
[boundary import or export](../boundaries.md) that requires one registration still fails build. Preferences cannot
choose a winner for either kind of error.
Reusing `select(filter, prefer=chain)` on a collection keeps the filter and **ignores the chain for membership**:
no preference callback runs and no members are removed or reordered. A member's own single dependency is a separate
choice and can use preferences. Collection and provider wrapper nodes remain the immediate parents; there is no
implicit ancestor search. Registration chains are skipped when a boundary masks their parent context, even for
an always-true predicate. Consumer chains see the public candidate view.

Predicates must be pure and synchronous. Every reached stage evaluates every survivor once, in existing order;
it stops as soon as one survivor remains. Unreachable later callbacks are intentionally skipped. Known async and
generator callbacks are rejected at declaration; unexpected deferred callback results or reached exceptions fail
build with the dependency path, phase and stage. Losing candidate graphs and eligibility callbacks still undergo
normal validation. Counts refer to one selection occurrence per compilation attempt; diagnostic retries are separate.

Successful build freezes choices. Activation and ordinary `new_scope()` do no preference work. Overlays can compile
new choices while inherited singleton plans retain their original dependencies and cleanup. Reports capture boolean
stage outcomes, missing or masked rules, elimination stages, and compact ranges of unreached stages without replaying
callbacks or exposing their closures. Graph fingerprints change with actual wiring, not equivalent predicate behavior.

Prefer a hard filter for requirements, mutually exclusive `when` rules for implementation validity, controlled
registration order for simple overrides, or numeric precedence for an explicit global priority. Chains are useful
when ordered preferences and valid fallback behavior are both necessary; they add coordination cost when supplied
by independent libraries.
