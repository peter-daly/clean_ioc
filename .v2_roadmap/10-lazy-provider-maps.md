# Lazy provider maps with callable keys

Status: Done; implemented and verified (timing precision limited by unrelated CPU load)
Priority: P1
Dependencies: Typed providers, resource ownership proof, Boundaries, type-alias support, canonical-key lookup fast paths
Assignment: lazy_provider_maps sub-agent with High reasoning

## Implementation outcome

The final API is `register_provider_map(service_type, *, key, key_type=str, asynchronous=False,
component_filter=all_components, name=None) -> str`. It declares a selectable transient map, keeps the existing
newest-first candidate order, and supports both Mapping spellings. The graph uses an additive `provider_map` node
with ordinary provider children; manifests remain unversioned during beta.

Final verification: 388 passing tests on Python 3.12, 3.13, and 3.14; 385 passing tests plus 3 native-syntax skips on
Python 3.11. The 38 new map cases, lint/format/type checks, documentation example validation, and diff checks pass.
All 48 benchmarks completed; repeated comparisons were run against an isolated pre-edit working-tree copy, preserving
the alias performance fix. Significant unrelated CPU load made timing deltas inconclusive; no precise regression bound
is claimed. Allocation peaks were essentially unchanged. See the local
[implementation/performance report](../.benchbro/provider-maps.XHF71w/REPORT.md) for raw comparisons and limitations,
and [supported API documentation](../docs/advanced/special-dependency-types.md#lazy-provider-maps).

## Objective

Implement the accepted provider-map idea: inject a read-only `Mapping[K, Provider[T]]` whose keys and target plans are
selected during compilation. Looking up a provider does not instantiate its target; calling that provider activates
only its selected target and dependencies. Also support `Mapping[K, AsyncProvider[T]]` with the same ownership rules.

This is accepted implementation work, not a release commitment. Generic registration patterns and assisted factories
are separate work. Scope context is already served by declared scope slots; do not introduce another context facility.

## Accepted public contract

- Add a builder operation anchored on the accepted spelling
  `builder.register_provider_map(PaymentGateway, key=lambda component: component.name)`.
- `key` is required and callable, not an attribute name, string selector, activated instance callback, or runtime resolver.
  It is a pure synchronous `Callable[[Component], K]`; `K` must be hashable and keep stable equality/hash behavior.
- Support typed constructor injection and root resolution using `collections.abc.Mapping` and the equivalent typing form.
  Do not redefine ordinary `dict` injection or existing eager mapping factories.
- The implementation agent should finalize and document the smallest coherent public signature before coding. Support
  explicit key-type information for non-string keys and empty maps without relying on an unannotated lambda's inferred
  return type. Preserve the simple string-name example above as the default use case. Choose and document an explicit
  sync/async declaration mechanism; do not infer provider mode from activated values.
- A declaration's target filter defaults to all visible eligible registrations, including named registrations. Offer an
  explicit component filter to narrow that set. Existing argument/root filters select map registrations, not a second
  dynamically chosen subset of their entries. Map registration names, if offered, retain ordinary registration semantics.
- Support normal ContainerBuilder, ScopeBuilder, and ComponentBuilder/bundle composition surfaces. Multiple declarations
  must have deterministic ordinary registration/selection behavior; never silently merge independently declared maps.
- Empty selected target sets produce an empty read-only mapping. Missing runtime keys raise normal `KeyError`.

Representative consumer; the exact declaration signature beyond the accepted shorthand is to be documented by the agent:

```python
from collections.abc import Mapping

from clean_ioc import ContainerBuilder, Provider


class PaymentGateway:
    pass


class StripeGateway(PaymentGateway):
    pass


class PayPalGateway(PaymentGateway):
    pass


class Checkout:
    def __init__(self, gateways: Mapping[str, Provider[PaymentGateway]]):
        self.gateways = gateways

    def select_gateway(self, name: str) -> PaymentGateway:
        return self.gateways[name]()


builder = ContainerBuilder()
builder.register(PaymentGateway, StripeGateway, name="stripe", lifespan="scoped")
builder.register(PaymentGateway, PayPalGateway, name="paypal", lifespan="scoped")
builder.register_provider_map(PaymentGateway, key=lambda component: component.name)
builder.register(Checkout)

with builder.build() as container:
    with container.new_scope() as scope:
        checkout = scope.resolve(Checkout)  # Neither gateway has been activated.
        gateway = checkout.select_gateway("stripe")  # Only StripeGateway is activated.
```

## Compiler, runtime, and ownership requirements

- Select targets using existing eligibility, decorator, generic specialization, and Boundary visibility rules. Compute keys
  from the selected target Component metadata, consistently with existing provider target filters. Preserve registration
  order for mapping iteration; do not sort arbitrary application keys.
- Freeze the mapping entries and a direct provider target step for every entry during build. Evaluate the key callable
  once per selected target occurrence within that map compilation; distinct occurrences, previews, retries, and fresh
  builds may evaluate it again. Do not make a global once-per-registration promise for occurrence-dependent selection.
- Reject duplicate keys using normal dictionary equality semantics, unhashable keys, async key callbacks/results, and
  callback/hash/equality failures with structured build issues. Do not invoke component constructors, activation
  factories, or providers to determine keys. Invalid declarations should fail through normal builder/build conventions.
- At runtime, mapping access and iteration must not call the key function, redo component filtering, discover registrations,
  compile targets, or activate targets. Freeze topology, not shared provider handles bound to the wrong runtime scope.
- Reuse the existing Provider/AsyncProvider invocation machinery: a fresh top-level resolution context per provider call,
  transient/per_resolution/scoped/singleton cache behavior, correct sync/async activation, and exactly-once resource cleanup.
- Validate every selected target graph during build. A synchronous map cannot hide an async-only target. A singleton
  consumer cannot retain a map whose providers reach forbidden scoped values, slots, Scope, or ResolutionContext. Safe
  singleton capture binds each provider to the appropriate owning scope just as an individually injected provider does.
- Escaped handles fail after their bound owner closes. Map iteration need not erase ordinary Python metadata after scope
  exit, but no provider may resurrect a closed scope or obtain a different current scope implicitly.
- Ordinary nested scopes keep current inheritance semantics. Overlay maps use their visible frozen plans and inherited
  parent singletons keep their anchored dependencies. A Boundary-local map cannot see private targets from another area.
- Use canonical types for aliases nested around maps, key types, providers, and targets. Preserve NewType service-key
  identity. Support existing closed generic targets, not the separate generic-pattern proposal.
- Preserve ordinary class and canonical generic/union/provider lookup fast paths. A program that does not declare a
  provider map must not pay new per-activation reflection, graph walking, callback dispatch, or map construction costs.

## Graph, diagnostics, and compatibility

- Expose the map and every selected provider/target relationship in the compiled graph. Ownership validation, explain,
  manifests, fingerprints, graph walks, and Boundary provenance must agree with the actual runtime steps. Do not hide
  the target set in a closure or opaque eager factory.
- Give map definitions and entry occurrences deterministic semantic identities that do not depend on runtime values,
  raw keys, random occurrence IDs, or arbitrary key reprs. Preserve the exact graph/fingerprint output of programs that
  do not use this feature. Keep manifests unversioned during beta and document any additive graph representation
  explicitly; do not add version checks or migration adapters.
- Keys may be derived from sensitive metadata/build inputs. Never emit raw keys, hashes of keys, configured values,
  callback exception messages, or arbitrary reprs in default manifests or errors. Diagnose collisions/failures using
  safe component paths and definition identities. Record key-type and provider-mode semantics and target topology;
  document that changes only to redacted computed key values cannot be inferred from the default fingerprint.
- Add stable lowercase hyphenated issue codes for invalid key callbacks, duplicate/unhashable keys, and key evaluation
  failure, retaining existing provider error codes where applicable. Failed compilation must leave builders repairable.
- No minimum-Python or dependency change, version bump, publication, or commit. Python 3.11 must still import all runtime
  modules and normally collected tests. Gate native alias syntax in tests as the existing suite does.

## Delivery and acceptance

Read current `V2_DEVELOPMENT.md`, provider/scopes/Boundary/type-alias docs, the implementation of provider steps and
ownership validation, and all applicable skill instructions before editing. Current code takes precedence over stale
proposal descriptions. Read using-typetoolbox for relevant generic work, use-assertive for tests when applicable, and
use-benchbro plus its required references before performance work. Do not delegate this assignment further.

Acceptance coverage must include:

- Named and filtered target sets, insertion order, empty maps, non-string keys, explicit map typing, and multiple map
  declarations with unambiguous selection; preserve all ordinary non-map registration and collection behavior.
- No activation when resolving/iterating a map, one selected target per call, sync and async maps, and safe handling of
  duplicate/unhashable/async/failing callbacks without private-value leakage. Assert runtime callbacks are never invoked.
- All lifespans, scoped identity, fresh per-resolution identity per invocation, managed sync/async resources, singleton
  capture restrictions, closure errors, nested scopes, scope slots, and overlays.
- Decorators, generic/union/NewType targets, native/backported aliases, root and constructor injection, Boundary visibility
  and exports, missing dependency failures in uncalled targets, recursive maps, and failed-build repair.
- Graph and explain fidelity, deterministic/redacted serialization and fingerprints, unchanged existing manifests, and
  no compiler/selection work when invoking a provider from an already built map.

Run focused tests and the full suite, ruff lint/format checks, ty, documentation example validation, and git diff --check.
Run relevant compatibility coverage on installed Python 3.11–3.14 without replacing the shared environment repeatedly.
Update supported docs, the example validator, and V2_DEVELOPMENT.md for the final public API.

Use BenchBro to capture a reference of the current **working tree**, including the uncommitted alias performance fix,
before implementation. HEAD does not include that work and is not the correct feature baseline. Preserve the working
tree in an isolated comparison copy if necessary, including untracked source/tests and benchmark files. Run performance
experiments sequentially and do not overlap them with test loads. Use dedicated named baselines and separate output
paths: `--no-compare` can still auto-backfill a baseline, so do not select or replace the user's historical local baseline.

Add focused benchmarks for map acquisition/key lookup/provider invocation and retain the existing lookup-path cases.
Compare relevant existing runtime/build cases before and after in the same environment, repeat suspicious changes, and
review sample quality and measured deltas rather than relying only on permissive default failure thresholds. Current
performance evidence is under `.benchbro/type-alias-fix.hdj4fn/`; those ignored artifacts are reference context, not
committed baselines or a substitute for a fresh pre-change measurement.

Preserve all existing uncommitted work. Mark this proposal and its index row Done only when implemented and verified;
otherwise report exact remaining gaps. Deliver the final API/examples, changed files, test and benchmark results, and
any compatibility or serialization limitations.
