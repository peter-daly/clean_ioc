# Modern Python type-alias support

Status: Done
Priority: P1
Dependencies: Existing type-form service keys, generic specialization, providers, Boundaries, and compilation provenance
Assignment: Completed by gpt-5.6-sol with Medium reasoning

## Summary

Support native Python `type` aliases and `typing_extensions.TypeAliasType` consistently wherever Clean IoC accepts a
service type or inspects a dependency annotation. An alias resolves to its underlying service key, including when nested
inside a generic, collection, union, factory signature, or provider. Preserve useful alias names in diagnostics while
using canonical types for graph semantics and fingerprints. `NewType` declarations retain distinct service identities.

This is an implementation handoff, not a release commitment. Implement this feature only; the accepted lazy provider
maps and generic registration patterns are separate work. Assisted factories remain in the maybe pile, and decorator
ordering remains controlled by `position`.

## Current repository and constraints

- Read `V2_DEVELOPMENT.md`, `docs/generics.md`, `docs/factories.md`, `docs/decorators.md`, and `docs/boundaries.md` before
  editing. Current code and tests take precedence over older roadmap descriptions of already implemented features.
- The package currently supports Python 3.11 through 3.14. Library modules and normally collected tests must remain
  parseable on Python 3.11. Use version-gated fixtures for native `type` syntax, following the existing generic tests.
- `typing_extensions` and `typetoolbox` are existing dependencies. Prefer their supported APIs and avoid a dependency
  or minimum-Python-version change. Read the repository's `using-typetoolbox` skill before generic implementation work.
- Public lifespan names are now `transient`, `per_resolution`, `scoped`, and `singleton`.
- Registries currently use type objects as keys. Generic factories, closed constructors, provider requests, boundary
  matching, scope slots, and tooling each inspect those keys; fixing only `register()` will leave inconsistent behavior.
- `docs/factories.md` explicitly excludes native `type`-statement unwrapping today. Remove that limitation when supported.
- There is existing uncommitted roadmap work. Preserve all existing changes, including changes made after this handoff.
  Do not create a commit, push, publish a package, or change the package version as part of this assignment.

## Goals and non-goals

Goals:

- Alias and underlying spelling work interchangeably for the same registered component and resolution request.
- Nested and parameterized aliases preserve correct generic bindings, selection, activation, and resource ownership.
- Named components, metadata filters, decorators, providers, scope slots, Boundaries, and overlays behave consistently.
- Missing and invalid alias dependencies produce actionable diagnostics and leave failed builders repairable.
- Existing non-alias APIs, graph manifests, and the common cached-resolution path keep their current behavior.

Non-goals:

- Creating a new registration-alias API, renaming components, or adding an alias activation node or runtime proxy.
- Automatically registering the members of a union or discovering registrations through structural protocol matching.
- Adding generic pattern selection, variance-based matching, ParamSpec, or TypeVarTuple specialization.
- Turning `Annotated` metadata into a new dependency-selection DSL.
- Supporting infinitely recursive service-key aliases in this release.
- Inferring a `NewType` key from a runtime value or applying implicit fallback to its supertype.

## Public behavior and examples

Existing public methods accept aliases; no new builder method is needed. Examples below specify future behavior.

### Native aliases, generic aliases, and shared identity

Python 3.12+:

```python
from clean_ioc import ContainerBuilder, Provider


class Order:
    pass


class Repository[T]:
    pass


type Repo[T] = Repository[T]
type OrderRepository = Repo[Order]


class Checkout:
    def __init__(self, repository: OrderRepository, create_repository: Provider[OrderRepository]):
        self.repository = repository
        self.create_repository = create_repository


builder = ContainerBuilder()
builder.register(OrderRepository, lifespan="singleton")
builder.register(Checkout)

with builder.build() as container:
    checkout = container.resolve(Checkout)
    assert checkout.repository is container.resolve(Repository[Order])
    assert container.resolve(Repo[Order]) is checkout.repository
    assert checkout.create_repository() is checkout.repository
```

Python 3.11 uses the existing backport and traditional generic syntax:

```python
from typing import Generic, TypeVar
from typing_extensions import TypeAliasType

T = TypeVar("T")


class Repository(Generic[T]):
    pass


Repo = TypeAliasType("Repo", Repository[T], type_params=(T,))
```

`Repo[int]` and `Repository[int]` must refer to the same registration. Registering through both spellings explicitly
still creates two registrations, just as registering the underlying type twice does today; normalization is not an
implicit deduplication or replacement policy.

### Union alias

```python
type RedisClient = StandaloneClient | ClusterClient

builder.register(RedisClient, factory=create_client, lifespan="singleton")
```

This registers the complete union key. Its members do not become separately registered. Aliased optional unions retain
the current Python-default and `inject()` behavior; unwrapping an alias does not introduce optional fallback injection.

### NewType stays distinct

```python
from typing import NewType
from clean_ioc import ContainerBuilder

DatabaseUrl = NewType("DatabaseUrl", str)
ApiUrl = NewType("ApiUrl", str)


class Settings:
    def __init__(self, database: DatabaseUrl, api: ApiUrl):
        self.database = database
        self.api = api


builder = ContainerBuilder()
builder.register(DatabaseUrl, instance=DatabaseUrl("postgresql://localhost/app"))
builder.register(ApiUrl, instance=ApiUrl("https://api.example"))
builder.register(Settings)
```

These are separate service keys even though their runtime values are strings. An alias of `DatabaseUrl` normalizes to
`DatabaseUrl`, never `str`. Support explicit instance and factory registrations under NewType keys. Do not treat a bare
NewType declaration as a constructor that automatically injects its underlying primitive; require an explicit activation
source, with a clear error if absent. Do not claim runtime type checks can distinguish differently labelled strings.

## Normalization contract

Use one internal normalization implementation at the relevant API and compiler boundaries. Keep declared annotation
information separately where needed for diagnostics; normalized type expressions drive registry and plan selection.

1. Recognize real native and backported TypeAliasType objects, including parameterized aliases whose origin is an alias.
   Do not unwrap arbitrary objects merely because they have an attribute named `__value__`.
2. Expand the alias value using its defining annotation context and Python's supported evaluation facilities.
3. Bind alias parameters to supplied arguments by parameter identity and lexical scope before expanding nested aliases.
   Reordered parameters, alias chains, and independently declared parameters with the same name must not be conflated.
4. Recursively normalize type positions in the result. Preserve the role of each expression: union alternatives,
   generic arguments, callable parameter lists, tuple ellipses, generator yields, and context-manager values.
5. Treat NewType objects as terminal nominal keys. Never follow `__supertype__` for registration matching.
6. Preserve current handling of unknown `Annotated` metadata: no new injection policy is inferred from it. Normalize
   its underlying type where annotations are already treated transparently. Never interpret `Literal` payloads or
   arbitrary annotation metadata as type aliases, and never serialize those payloads through new diagnostic fields.
7. Require normalization to be idempotent. Reusing a canonical type must not repeatedly rebuild the same structure.

Closed aliases must work everywhere their expanded type is already supported. An alias does not make an otherwise
unsupported dependency shape supported. A class-valued alias used with `register(Alias)` constructs the underlying class;
an alias expanding to a union follows the existing explicit-activation requirement. Apply the same principle to an
alias passed as `implementation_type`, a decorator class, or a factory specialization source.

For open generic aliases, expose only the template behavior the canonical target already supports. Preserve unresolved
parameters in a template and require a complete binding for a concrete dependency. Do not silently replace missing
parameters with `Any`. Honor defaults when provided by the supported Python or backport API; do not invent defaults.
Wrong arity or unsupported parameter kinds must fail clearly. This work does not add a new generic constraint solver.

The existing public `Component.generic_mapping` remains the canonical service mapping. Alias-local parameter names are
substitution inputs, not extra keys merged into that map. Normalize before invoking `GenericTypeMap` and related
typetoolbox APIs. Address alias-local name collisions without silently redefining the documented mapping behavior for
unrelated pre-existing generic class hierarchies.

## Lazy evaluation, forward references, and recursion

Native aliases evaluate their value lazily. Keep declarations available until the build snapshot so a forward reference
that becomes resolvable after registration but before `build()` can succeed. Preview methods may normalize in their
temporary compilation, but must not permanently cache a failure or make the builder unusable.

Resolve forward references in their defining namespace, including backport alias values where the necessary namespace
is available. Do not search arbitrary caller frames, import unrelated modules, or invent a namespace. Unresolvable
references produce `type-alias-unresolved` with safe alias and dependency labels. Support a repaired namespace on build
retry. Type annotation evaluation follows Python's semantics and may itself execute annotation expressions; the
container must never invoke an activation factory or constructor merely to identify an alias's service type.

Use cycle detection and a bounded expansion guard. Report direct recursion, mutual recursion, and growing generic
recursion as `type-alias-recursive`, including a finite alias chain. Do not reject a finite nested application such as
`Identity[Identity[int]]` merely because the same generic alias occurs twice. Do not leak a raw RecursionError.

## Integration checklist

| Surface | Required behavior |
| --- | --- |
| Registration and patching | Normalize service and class-valued implementation keys; preserve component IDs, registration order, names, and tags. Patching via either spelling finds the same definition. |
| Constructor and factory annotations | Normalize nested dependencies and factory result annotations before generic inference and ownership analysis. Keep original callable execution and its signature semantics. |
| Argument policies | `ParameterContext.annotation` is the specialized canonical annotation. `select`, `inject`, defaults, `derive`, and `generic_arg` retain their existing contracts. |
| Decorators and pre-configuration | Match alias and canonical service targets identically, including wrapped-argument inference, callable result checks, generic decorators, patching, and removal. Keep `position` ordering. |
| Providers and factory helpers | Unwrap aliases both around providers and inside their targets. `use_component` helpers use canonical target keys and keep visible compiled edges. |
| Collections and unions | Normalize nested element/member types while retaining existing collection synthesis and explicit union-key behavior. |
| Filters and preview queries | `cf.service_type_is(Alias)` and type-based built-in filters compare canonical types. `has_component`, ID queries, and previews accept either spelling. |
| Scope slots and runtime lookup | Slot declaration, `provide`, provision checks, root selection, sync/async resolve, and ResolutionContext all agree on canonical keys. |
| Boundaries | Normalize Expose, Use, and Use.root targets without changing visibility, source ownership, or names. An alias cannot expose a private registration. |
| Overlays | Alias spelling cannot bypass parent-singleton anchoring, create a second cache, or change captured parent dependencies. |
| Entry points and tooling | Canonical roots deduplicate marker spellings as current behavior requires. Explanations and CLI service locators accept aliases; all-root views remain complete. |

`Component.service_type` is canonical. Arbitrary user lambdas comparing raw alias objects cannot be rewritten; document
using `cf.service_type_is(Alias)` when alias-aware comparison is required. Factory outputs and supplied instance values
are never traversed or transformed by type normalization.

## Runtime, graph, and privacy decisions

- Normalization changes selection keys, not registration identity. All caches, ownership proofs, and resource cleanup
  execute the same compiled component plan regardless of request spelling.
- Resolving a previously unseen alias spelling of an already compiled type is allowed. Normalize its type expression
  at the existing non-class lookup boundary, then select a frozen plan; never compile a new generic specialization,
  discover registrations, reevaluate component filters for deferred targets, or mutate the blueprint at runtime.
- Invalid runtime-only alias requests fail with a clear lookup/input error carrying the relevant alias issue code;
  they must not raise a misleading successful-build report or modify the container.
- Preserve the existing direct path for ordinary class resolutions. Avoid adding a recursive normalization call to each
  already compiled activation step. Any memoization must be thread-safe, bounded or scoped, and must not retain failed
  alias evaluations or arbitrary application frames indefinitely.
- Store declared alias labels in diagnostic/provenance information, including the relevant original dependency spelling.
  Explain output should be able to show `OrderRepository -> Repository[Order]`. Preserve normalized graph semantics and
  avoid a new alias ComponentKind or proxy edge. Default fingerprint input excludes alias labels and source locations.
- A graph composed with an alias and an equivalent graph composed with its target must have identical canonical
  manifests and fingerprints, assuming the same underlying definitions and ordering. Alias-only renaming causes no
  semantic graph diff. NewType identities remain distinct and use deterministic qualified names in serialized output.
- Graph manifests remain unversioned during beta. Alias display belongs outside the manifest; do not add schema
  versioning or alter non-alias snapshots for this feature.
- Error reporting must not copy configured values, build inputs, alias evaluation exception messages, arbitrary object
  reprs, or source paths into default manifests. Format known type and alias names safely.

## Errors and failure behavior

- `type-alias-unresolved`: the alias value or a required forward reference cannot be resolved in its defining context.
- `type-alias-recursive`: alias expansion cycles or exceeds its bounded expansion limit.
- `type-alias-invalid`: an evaluated alias target is not a supported type expression or a normalization step fails.
- `type-alias-arguments`: alias parameter arity or required bindings are invalid at the point they are needed.
- `type-alias-unsupported-parameter`: expansion requires unsupported ParamSpec/TypeVarTuple behavior.

Aggregate alias errors discovered during compilation into ContainerBuildError.report with the owning dependency path.
If Python rejects the alias expression before a container API is called, its native error naturally applies. Preserve
ordinary missing-component, captive-dependency, scope-closure, and provider errors after successful normalization.

## Implementation stages and likely files

1. Add an internal alias/type normalization layer with native/backport detection, parameter substitution, safe diagnostic
   labels, and recursion handling. Integrate it with `generic_utils.py`; a separate private module is preferable if
   needed to prevent import cycles between components, container, and tooling.
2. Preserve declarations in builder snapshots where lazy alias evaluation requires it, and normalize during compilation
   before registry grouping and matching. Cover `_legacy.py` parsing, constructor recognition, generic factories, and
   metadata in `container.py`, `components.py`, and `arguments.py` as needed.
3. Wire all public selection paths and synthetic dependency forms through the same semantics: filters, providers,
   factory helpers, decorators, pre-configurations, slots, Boundaries, overlays, and runtime non-class requests.
4. Add alias-aware diagnostics and canonical tooling serialization. Extend existing CLI locator handling where it
   incorrectly assumes every service locator is a class. Do not change callable/builder import-locator behavior.
5. Add behavioral tests and documentation, update the docs example validator, and complete verification. Mark this
   proposal Done only after all required behavior and supported-version checks pass; otherwise record remaining gaps.

## Acceptance tests

- Register using an alias and resolve/inject using its target, and the reverse; cover aliases introduced only at runtime.
- Native and backport aliases behave identically on versions supporting them; no Python 3.12 syntax breaks 3.11 imports.
- Cover alias chains, generic aliases with nested/reordered arguments, aliases nested in canonical generic arguments,
  independent alias parameters sharing a name, and supported parameter defaults.
- Cover constructor aliases, inherited closed constructors, factory return aliases, explicit factory specialization,
  decorated generic targets, and sync/async generator and context-manager factories.
- Cover aliases around and inside Provider and AsyncProvider, collection aliases and aliased elements, union aliases,
  reversed equivalent union members, optional defaults, and explicit injection over a default.
- Verify names, tags, custom selection, built-in type filters, component IDs, preview queries, and patch/remove behavior.
- Verify root slots declared with an alias and provided with the target, the reverse, duplicate provision, and closed
  scope behavior; include aliases in Boundary Use/Expose declarations and inherited overlay registrations.
- Verify cache sharing across alias spellings at singleton, scoped, and per-resolution lifespans, transient behavior,
  unchanged owner routing, exactly-once finalization, and captive dependency rejection through aliases.
- Keep NewType keys distinct from each other and their supertypes in ordinary roots, providers, unions, generic
  specializations, slots, and alias-of-NewType requests. No accidental construction or primitive-key fallback occurs.
- Verify recursion, growing recursion, wrong arity, unsupported parameters, non-type values, unresolved forward
  references, successful late binding, and successful retry after an alias-related failed build.
- Verify unknown Annotated metadata follows existing semantics, Literal payloads are not evaluated as types, and no
  private values leak through normalization diagnostics or fingerprints.
- Alias-based and canonical compositions produce identical manifests, fingerprints, and semantic paths, including entry
  points, Boundary contracts, and provider nodes. Explain still retains useful declared alias labels.
- Demonstrate that alias-only renames do not change fingerprints, and NewType changes do affect semantic identities.
- Retain precise public type inference for alias resolution and factory/instance registration; use TypeForm where
  appropriate and avoid hiding public typing regressions behind broad Any annotations or test suppressions.
- After build, prohibit compiler/discovery calls in tests and verify alias requests execute the frozen plans. Preserve
  existing ordinary class resolution behavior and do not create activation-time alias graph work.

## Verification and delivery

Add focused tests in `tests/test_type_aliases.py` and extend nearby tests where integration belongs. Follow applicable
test skills when writing tests. Native-syntax fixtures should be isolated and gated by interpreter capability, following
the existing repository pattern; primary behavior tests should also exercise the backport on Python 3.11.

Run focused alias tests plus generic constructors, unions, providers, Boundaries, ownership, and compiler tooling, then
the full unit suite, Ruff checks/format checks, `ty check`, and `scripts/validate_docs_examples.py`. Run alias and relevant
compatibility tests on installed Python 3.11, 3.12, 3.13, and 3.14 using isolated environments so the shared environment
is not repeatedly replaced. Execute repository-required CI checks and `git diff --check`; report any unavailable check
explicitly. If performance measurements are needed, follow the BenchBro skill and use existing cases.

Update the relevant supported docs and `V2_DEVELOPMENT.md`, replacing the current explicit exclusion of native aliases.
Use examples that need no external service connection. Update the roadmap index/status and supply a handoff report
listing final public behavior, implementation choices, changed files, exact checks/results, and any limitations.

## Reference semantics

- [Python TypeAliasType documentation](https://docs.python.org/3/library/typing.html#typing.TypeAliasType) defines native
  alias parameters and lazy value evaluation. Handle interpreter differences explicitly.
- [Python typing specification: aliases and NewType](https://typing.python.org/en/latest/spec/aliases.html) distinguishes
  equivalent type aliases from nominal NewType declarations. This proposal applies that distinction to DI service keys.
- [typing_extensions documentation](https://typing-extensions.readthedocs.io/en/latest/#typing_extensions.TypeAliasType)
  describes the backport available to Python 3.11 callers.
