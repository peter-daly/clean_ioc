# Generic registration patterns

Status: Done (implementation); performance verification inconclusive under shared-machine noise
Priority: P1
Dependencies: Generic factory specialization, type-alias support, resource ownership proof, typed providers, Boundaries
Assignment: generic_registration_patterns sub-agent with High reasoning

## Finalized implementation contract

The implemented signature is `register_pattern(service_type, *, factory, lifespan="per_resolution", name=None,
arguments=None, tags=None, when=all_components) -> str`, on `ContainerBuilder`, `ScopeBuilder`, and `ComponentBuilder`.
The ID identifies the template and supports `patch_component(pattern, id, ...)`; closed specializations have stable
separate cache IDs. No additional public registration class or explicit specialization argument is needed.

Matching supports class origins, ordered arguments, fixed tuples, identity-bound TypeVars, repeated-variable equality,
transparent aliases, and nominal NewTypes. Ordinary class bounds/constraints use subclass inclusion; parameterized,
forward, and protocol bounds are explicitly unsupported. Union/Any/Literal/Annotated/Callable/ellipsis/bare-generic,
ParamSpec, and TypeVarTuple pattern structures are rejected. Factory variables must belong to the template by identity;
name collisions are diagnosed before bridging to existing name-based substitution. Factory result annotations must
substitute to the selected closed service. The public generic mapping remains service-oriented.

Specificity uses structural subsumption, not scores: `Serializer[list[T]]` is narrower than `Serializer[U]`, and
`Serializer[tuple[T, T]]` is narrower than `Serializer[tuple[T, U]]`. Narrower class bound/constraint domains also count.
`Serializer[tuple[int, T]]` and `Serializer[tuple[U, str]]` are incomparable for `Serializer[tuple[int, str]]` and fail
deterministically. Equivalent patterns preserve all registrations and ordinary newest-first/layer ordering.

Visibility precedes exact/pattern/open tier selection and specificity. Existing `when`, caller/name filters, collections,
and map target filters apply afterwards without creating a new fallback. Closed public dependency/provider/map requests
compile as public pattern roots. Private dependencies remain private. Entry-point markers focus existing compiled pattern
requests and do not introduce new keys. Boundaries accept explicitly closed Expose/Use targets only for structural
templates; open pattern visibility declarations are rejected. Definition-site dependencies and anchored parent singletons
retain their existing semantics.

Non-shrinking expansion is bounded after 16 active specializations of one template or 32 across all templates,
with a separate diagnostic from
ordinary dependency cycles. This is a conservative guard rather than a general termination proof; finite shrinking
nesting beyond that depth is tested. All matching and binding remain in compilation, and no known-key runtime lookup
method was changed. Four non-pattern manifests (core, Boundary, provider, resource ownership) match the captured
working-tree reference byte for byte.

Implementation checks pass on Python 3.11–3.14: 454 tests on 3.12/3.13/3.14; 450 passed and four native-syntax skips
on 3.11. The 59 new pattern cases cover the supported API, matching, visibility, ownership, frozen runtime behavior,
diagnostics, and repair. Ruff lint/format, ty, executable documentation examples, strict MkDocs, pre-commit, package
build, and `git diff --check` pass. Existing dependency deprecation notices remain.

Performance verification is **inconclusive**. All 46 existing cases and 16 focused pattern/control cases completed;
28 existing cases were repeated in alternating reference/current runs with 30 fixed samples. Timing changes did not
remain stable: the unchanged direct-Python control shifted +40.8%, and some timing CVs exceeded 60%. Python allocation
peaks were steady. No existing runtime activation/lookup path changed. Full raw measurements, paired comparisons,
focused costs, and quiet-machine rerun conditions are in the ignored experiment's
[report](../.benchbro/generic-patterns.cTvm87/REPORT.md). Do not interpret successful CLI exits as proof of no regression.

## Objective and scope

Add structural registration templates such as `Serializer[list[T]]` and `Serializer[dict[str, T]]`. A closed dependency
request chooses a matching template during compilation, binds its variables, and compiles the factory's substituted
dependencies. This extends existing open-generic factory specialization; it does not introduce runtime type dispatch.

Implement the accepted factory-based API, anchored on
`builder.register_pattern(Serializer[list[T]], factory=make_list_serializer)`. Choose the smallest coherent signature
consistent with ordinary registration, including names, tags, lifespans, argument configuration, and `when` conditions.
Support the normal container, scope-overlay, and bundle composition surfaces. Return a registration identity consistent
with existing builder operations. A public class named `GenericPatternRegistrations` is not required.

Constructor-template syntax, assisted factories, relative decorator ordering, runtime registration, subclass discovery
changes, ParamSpec, and TypeVarTuple matching are outside this assignment. Do not add a new scope-context mechanism.

## Representative usage

The following is the intended public shape, to be made executable in supported documentation and its validator:

```python
from dataclasses import dataclass
from typing import Generic, TypeVar

from clean_ioc import ContainerBuilder

T = TypeVar("T")


class Serializer(Generic[T]):
    def serialize(self, value: T) -> str:
        raise NotImplementedError


@dataclass
class Order:
    reference: str


class OrderSerializer(Serializer[Order]):
    def serialize(self, value: Order) -> str:
        return value.reference


class ListSerializer(Serializer[list[T]]):
    def __init__(self, item_serializer: Serializer[T]):
        self.item_serializer = item_serializer

    def serialize(self, value: list[T]) -> str:
        return "[" + ", ".join(self.item_serializer.serialize(item) for item in value) + "]"


def make_list_serializer(item_serializer: Serializer[T]) -> Serializer[list[T]]:
    return ListSerializer(item_serializer)


class ExportOrders:
    def __init__(self, serializer: Serializer[list[Order]]):
        self.serializer = serializer


builder = ContainerBuilder()
builder.register(Serializer[Order], OrderSerializer)
builder.register_pattern(Serializer[list[T]], factory=make_list_serializer)
builder.register(ExportOrders)

with builder.build() as container:
    exporter = container.resolve(ExportOrders)
    assert exporter.serializer.serialize([Order("A"), Order("B")]) == "[A, B]"
```

The same template should handle finite nesting such as `Serializer[list[list[Order]]]` without manual intermediate
registrations. A separate dictionary pattern must match `dict[str, T]`, not every dictionary key type.

## Matching and selection contract

- Normalize transparent native/backported aliases before matching; retain nominal NewType identity. Preserve current
  Python 3.11 support and the existing rule that a bare generic is not implicitly closed from TypeVar defaults.
- Match type structure by canonical origin and ordered arguments. Concrete positions must match; TypeVars bind requested
  closed subexpressions. Repeated occurrences of one TypeVar must bind equally. Do not add variance-based or arbitrary
  subclass dispatch for concrete positions.
- Validate declared TypeVar bounds and constraints at build time. Define the supported forms explicitly, including safe
  handling of non-runtime-checkable protocols and parameterized bounds; reject unsupported forms rather than silently
  accepting them. Unsupported annotation structures must produce clear diagnostics, not accidental matches.
- Track pattern-variable identity during matching. Existing GenericTypeMap metadata is name-based: retain its current
  documented limitations and diagnose collisions when bridging bindings, rather than merging unrelated same-named
  TypeVars. Preserve the distinction between service-variable metadata and implementation/factory bindings.
- Exact closed registrations take precedence over structural patterns; matching patterns take precedence over existing
  open-generic fallbacks. Programs without patterns must retain current selection behavior.
- Prefer a structurally more specific matching pattern over a more general one. Ambiguous incomparable structures must
  fail deterministically; do not use registration order, arbitrary numerical scores, or factory execution to choose one.
  Define and test this relation before coding, including overlapping nested patterns and bounds/constraints.
- Multiple registrations of the same canonical pattern retain normal multi-binding, naming, filtering, and ordering
  behavior; they must not become an accidental single-registration feature. Document exactly how visibility, `when`,
  caller filters, and overlay priority interact with pattern precedence. In particular, rejecting an exact registration
  with a caller's name filter must not silently invent a new pattern fallback contrary to existing selection semantics.
- Infer factory dependency substitutions from the pattern's binding, not just positional arguments of the outer service.
  Diagnose unresolved or conflicting factory variables. Honor existing explicit argument configuration and preserve the
  original factory object; do not invoke factories or constructors during matching or validation.

## Compilation, runtime, and ownership

- Discover the finite set of required closed specializations through existing compilation requests. A template alone
  must not enumerate an infinite universe of types or become a directly activatable open root. Document precisely which
  compiled closed requests can be resolved as public roots. Keep `mark_entrypoint()` a tooling declaration, not a runtime
  access grant or a mandatory new registration step.
- Freeze every selected specialized plan during build. Unseen closed requests cannot trigger matching, discovery, or
  compilation at runtime. Do not add reflection or a pattern-registry check to existing known-key resolution fast paths.
- Detect ordinary dependency cycles and non-terminating type growth separately. Finite shrinking nesting must work;
  a factory that expands `Serializer[T]` into `Serializer[list[T]]` must fail with a bounded, useful diagnostic rather
  than RecursionError or an unbounded build. Avoid process-global specialization caches or leaks across builders.
- Keep stable cache identities per template registration and canonical closed specialization. Repeated occurrences of
  one specialization share according to its lifespan; different specializations must not accidentally share instances.
- Apply existing decorators, generic metadata, validation, resource ownership, sync/async activation, cleanup, and
  pre-configuration behavior to specialized components. No new lifecycle semantics are introduced.
- Typed providers and provider maps must compile and validate their selected closed pattern targets even when never
  invoked. Pattern matching must not run when a provider is called or a map key is looked up.
- Respect current Boundary imports/exports and definition-site visibility when selecting templates and their
  dependencies. Do not expose private registrations or create a new template-export wildcard. Cover closed requests at
  visibility boundaries and document any explicitly rejected unsupported exposure shape.
- Scope overlays retain their current ordering and anchored-parent-singleton rules. Child templates cannot retarget an
  already compiled parent singleton. Builders remain repairable after failed preview/build, and successful runtimes
  remain frozen even if new subclasses or definitions appear later.

## Graph, diagnostics, privacy, and compatibility

- Graph components must show the actual closed service, factory, substituted dependencies, and existing ownership facts.
  Explain must identify the winning template and rejected/mismatched/less-specific alternatives with safe reasoning.
- Introduce stable lowercase hyphenated issue codes for invalid patterns, unsupported matching forms, incompatible
  bindings, ambiguous patterns, and non-terminating expansion; reuse existing dependency/lifetime errors where applicable.
  Include the closed request and safe compilation path, not arbitrary values or callback exception messages.
- Preserve deterministic semantic identities, manifests, and fingerprints. Template provenance and source locations must
  not enter default fingerprints. Inputs, configured values, runtime instances, and arbitrary reprs remain redacted.
- Follow the repository's current beta decision: JSON formats are unversioned. Do not restore schema version fields,
  version checks, or migration adapters. Preserve exact manifests for programs that do not use patterns.
- Keep modern alias normalization and known-key lookup optimizations intact. Do not change Python requirements,
  dependencies, package versions, unrelated public APIs, or the existing Boundaries terminology.

## Implementation stages and acceptance tests

1. Read current generic/factory, provider-map, Boundary, ownership, and type-alias code/docs plus V2_DEVELOPMENT.md.
   Record the finalized public signature, supported matching forms, specificity examples, and filtering rules here.
   Capture a pre-edit snapshot of the entire relevant working tree for benchmarks; HEAD is not the correct baseline.
2. Implement structural binding and selection with focused tests, then integrate specialized plans with ordinary compiler
   behavior. Keep optional-feature costs in compilation and avoid new branches on ordinary activation paths.
3. Cover public builder/bundle APIs, real list/dictionary examples, finite nesting, concrete/repeated variable positions,
   aliases and NewType, bounds/constraints, same-named variable rejection, unsupported forms, and factory binding errors.
4. Cover exact/pattern/open precedence, specificity and ambiguity, registration ordering, named collections, filters,
   conditions, decorators, exports/imports, overlays, direct roots, all lifespans, sync/async resource factories,
   providers/maps, private targets, missing dependencies, growing recursion, and failed-build repair.
5. Verify graph/explain fidelity, redaction, deterministic fingerprints, and unchanged non-pattern manifests. Prove
   factories are not activated by build and pattern matching never occurs during runtime resolution.
6. Run focused tests and the full suite, lint/format checks, ty, documentation example validation, compatibility coverage
   on installed supported Python versions, and git diff --check. Update supported generic docs and example validation,
   V2_DEVELOPMENT.md, and this proposal/index with the actual implementation outcome.
7. Run and interpret the before/after benchmarks below. Fix any reproducible regression caused by this feature, then
   rerun correctness and performance checks. Deliver results with remaining limitations stated explicitly.

Read using-typetoolbox for generic work, use-assertive when applicable to tests, and use-benchbro plus its required
references before performance work. Do not delegate this assignment further. Preserve all current uncommitted work,
including untracked source and the in-progress/finished Boundaries renames. Do not commit, push, or publish.

## Required benchmark verification

Benchmarking is part of this assignment, not an optional follow-up. Compare against the current working tree, which
already includes aliases, their lookup-performance fix, lazy provider maps, and the latest Boundary/tooling changes.
Preserve an isolated reference before implementation so both revisions can be remeasured in the same environment.

- Use BenchBro's installed CLI/public interface and dedicated named baselines with output under a new ignored
  `.benchbro/` experiment directory. Do not replace historical baselines or tracked benchmark reports; `--no-compare`
  can still backfill the selected baseline.
- Run existing runtime, build, tooling, allocation, canonical lookup-path, and provider-map cases before and after.
  Add focused pattern-build cases for different nesting depths and overlapping template sets, plus frozen runtime
  resolution cases. For new-only cases, report absolute cost and a comparable explicit-registration control rather
  than inventing a pre-feature measurement.
- Run measurements sequentially, without simultaneous tests or other agent benchmarks. Keep interpreter, dependencies,
  benchmark definitions/settings, and environment comparable; measure unchanged code repeatedly to establish noise.
- Inspect medians, sample quality, confidence, CV, and allocations. BenchBro's default 50% warning/100% failure thresholds
  and a zero exit code are not sufficient evidence that performance has not regressed. Repeat suspicious changes with
  alternating reference/current runs where useful and investigate reproducible feature-related slowdowns.
- The previous provider-map timings were inconclusive under heavy unrelated CPU load; see the local report at
  `.benchbro/provider-maps.XHF71w/REPORT.md`. Do not reuse those noisy numbers as a clean baseline. Do not stop unrelated
  user processes. If interference prevents a defensible conclusion after reasonable repeated measurements, report
  benchmark validation as inconclusive, with the affected cases and concrete rerun conditions, rather than claiming
  no regression.

Final delivery must include the supported API/example, tests and compatibility results, before/after performance
summary with links to raw local reports, and any unresolved correctness or measurement gaps. Mark the implementation
Done only when its functional checks pass; record performance verification separately and honestly if still blocked
by measurement noise.
