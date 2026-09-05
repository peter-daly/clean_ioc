# Graph-correlated activation tracing

Status: Proposal
Priority: P2
Dependencies: Compilation provenance; resource ownership proof
Optional integration: OpenTelemetry

## Summary

Compile a separate opt-in instrumented activation plan that emits redacted resolution, activation, cache, wait, and
cleanup events identified by graph fingerprint and semantic component path. The default uninstrumented steps retain a
branch-free hot path.

## Problem and differentiation

The compiled graph explains what can execute, but production diagnostics cannot currently correlate slow activation,
cache contention, failures, or cleanup with that exact plan. Generic tracing around `resolve()` loses component identity;
wrapping factories manually changes application code and misses cache and finalizer behavior.

Stable graph-correlated events connect architecture reviewed in CI with runtime evidence while keeping application
components free of Clean IoC instrumentation.

## Goals

- Trace top-level resolutions and individual component activation using stable semantic graph identities.
- Observe cache hits, coordinated cache waits, pre-configuration, activation failures, and cleanup.
- Provide a small observer API and an optional OpenTelemetry adapter.
- Exclude values, build inputs, runtime object identities, and exception messages by default.
- Add no observer branch or event allocation to an uninstrumented plan.

## Non-goals

- Distributed tracing without an installed telemetry implementation.
- Inspecting method calls after dependency activation.
- Serializing dependency instances or constructor arguments.
- Turning runtime traces into graph manifests or build validation results automatically.
- Guaranteeing zero overhead when instrumentation is enabled.

## User stories

- A trace identifies which compiled factory made first-request startup slow.
- Operators distinguish a slow singleton constructor from time spent waiting for another task to initialize it.
- A cleanup failure links to the same semantic component path reviewed in the deployment graph.
- Two deployments can group metrics by graph fingerprint without revealing configuration values.

## Public API

Add `clean_ioc.instrumentation`:

```python
from clean_ioc.instrumentation import (
    ActivationEvent,
    ActivationEventKind,
    ActivationObserver,
    Instrumentation,
)


class JsonObserver:
    def on_event(self, event: ActivationEvent) -> None:
        write_json(event.to_dict())


container = builder.build(
    build_args={"environment": "production"},
    instrumentation=Instrumentation(observer=JsonObserver()),
)
```

`ContainerBuilder.build()` and `ScopeBuilder.build()` gain the independent optional keyword
`instrumentation: Instrumentation | None = None`. It is not included in `build_args`, filters, components, manifests, or
fingerprints.

The immutable event model is:

```python
class ActivationEventKind(str, Enum):
    resolution_started = "resolution-started"
    resolution_finished = "resolution-finished"
    activation_started = "activation-started"
    activation_finished = "activation-finished"
    activation_failed = "activation-failed"
    cache_hit = "cache-hit"
    cache_wait_started = "cache-wait-started"
    cache_wait_finished = "cache-wait-finished"
    pre_configuration_started = "pre-configuration-started"
    pre_configuration_finished = "pre-configuration-finished"
    cleanup_started = "cleanup-started"
    cleanup_finished = "cleanup-finished"
    cleanup_failed = "cleanup-failed"


@dataclass(frozen=True, slots=True)
class ActivationEvent:
    kind: ActivationEventKind
    graph_fingerprint: str
    root: str
    component_path: str | None
    component_kind: str | None
    activation: str | None
    lifespan: str | None
    duration_ns: int | None
    exception_type: str | None

    def to_dict(self) -> dict[str, object]: ...


class ActivationObserver(Protocol):
    def on_event(self, event: ActivationEvent) -> None: ...


@dataclass(frozen=True, slots=True)
class Instrumentation:
    observer: ActivationObserver | None
    component_filter: ComponentFilter = all_components
    sampler: ResolutionSampler = always_sample
    include_cache_hits: bool = True

    @classmethod
    def disabled(cls) -> Instrumentation: ...
```

`ResolutionSampler` is a synchronous, side-effect-free callback receiving only the qualified requested root type and
returning a boolean. It runs once per top-level `resolve`, `resolve_async`, or typed-provider call. Sampling decisions are
not cached across calls.

## Compiled execution model

When `instrumentation is None`, the compiler emits the existing specialized `_Step` classes exactly. There is no
nullable observer field, sampling check, timing call, wrapper, or event allocation on their resolve paths.

When instrumentation is enabled, the compiler emits distinct observed step implementations with direct observer and
semantic-path references. Those steps:

- sample once at the top-level resolution boundary;
- use a monotonic high-resolution clock only for sampled operations;
- emit activation events around user constructors, factories, generators, context managers, and decorators;
- emit separate pre-configuration events;
- distinguish a cache hit from waiting on the scoped/singleton coordinator;
- retain normal activation, retry, cancellation, and ownership semantics.

Instrumentation is runtime metadata attached to the plan, not a component. It cannot be injected, selected, decorated,
or reached through `ResolutionContext`.

An ordinary child scope inherits the parent's instrumentation because it reuses the plan. A compiled overlay uses the
`instrumentation=` value supplied to its `ScopeBuilder.build()`; omission inherits the parent observer and sampling
configuration. Passing `Instrumentation.disabled()` explicitly creates an uninstrumented overlay plan.

## Event semantics

One sampled top-level request emits `resolution_started` and exactly one `resolution_finished`, including failed and
cancelled resolutions. `resolution_finished` carries duration and an exception type when applicable.

Activation events surround user activation only; dependency-resolution time appears in child events and the containing
resolution duration. A cached value emits `cache_hit` but no activation pair. The task or thread that wins initialization
emits activation events; waiters emit cache-wait events and then either a hit-equivalent finish or the propagated failure.

Cleanup occurs when an owner closes, potentially long after the resolution trace. It emits a new cleanup operation keyed
by graph fingerprint and component path. The runtime does not retain original trace contexts per cached object. Finalizer
order and exception aggregation remain controlled by the ownership proposal.

Observer calls are synchronous and must return promptly. An observer exception never changes resolution or cleanup. The
runtime logs the first observer failure through the `clean_ioc.instrumentation` logger, disables that observer for the
affected scope owner, and continues without further events from it.

## OpenTelemetry adapter

Provide an optional `clean_ioc.ext.opentelemetry` package and packaging extra. The adapter maps:

- each sampled top-level resolution to a `clean_ioc.resolve` span;
- actual component activation to nested `clean_ioc.activate` spans;
- cache hits and waits to span events, with wait duration;
- pre-configurations to `clean_ioc.pre_configure` spans;
- owner close to `clean_ioc.cleanup` spans with component child spans.

Attributes use the `clean_ioc.*` namespace and include graph fingerprint, root type, semantic path, component kind,
activation kind, and lifespan. The adapter uses the caller's current OpenTelemetry context but does not install global
providers or exporters.

OpenTelemetry status is error for activation or cleanup failures. Only the qualified exception type is recorded by
default; stack traces and exception messages require an explicit adapter option because they may contain application
data.

## Privacy and cardinality

- Semantic paths and qualified types come from the redacted manifest model.
- Build-argument keys and values, constructor arguments, provided slot values, returned objects, object IDs, scope IDs,
  owner tokens, filter state, and callable representations are never event fields.
- Graph fingerprint is stable for one manifest and contains no secret input.
- Exception messages and stack traces are disabled by default.
- `component_filter` and sampling control volume; they do not change the compiled graph or fingerprint.
- Observers are responsible for exporter-level attribute and retention policy.

## Errors and failure modes

- `instrumentation-invalid-observer`: the observer lacks a callable `on_event` method.
- `instrumentation-invalid-sampler`: the sampler is malformed; detected before the runtime is returned.
- Observer and sampler exceptions do not become component activation errors. A sampler exception disables sampling for
  that resolution and follows the same one-time logging policy.
- Event timestamps and durations are process-local telemetry and are never used for build decisions.
- Cancellation produces a finished event with the qualified cancellation exception type, then propagates normally.

## Compatibility

Instrumentation is opt-in and does not alter manifests, fingerprints, component selection, ownership, cache keys, or
public application types. The optional OpenTelemetry dependency is not installed with the base package. Existing build
calls remain valid.

## Rejected alternatives

- **One optional observer check in every existing step:** even a predictable branch weakens the uninstrumented hot-path
  guarantee and invites accidental event allocation.
- **Wrap user factories:** wrappers obscure component identity and miss cache waits, pre-configurations, and cleanup.
- **Record runtime values for debugging:** DI values commonly contain credentials, requests, and personal data.
- **Retain original trace contexts until cleanup:** long-lived singletons would retain application tracing state.
- **Let observer failures fail resolution:** telemetry must not become an application dependency.

## Rollout

1. Add the event model and observed transient/once-per-graph steps behind explicit instrumentation.
2. Cover scoped/singleton coordination, pre-configurations, decorators, and provider calls.
3. Add ownership-aware cleanup events and overlay inheritance/disable behavior.
4. Add the optional OpenTelemetry adapter, documentation, and instrumented/uninstrumented benchmarks.

## Acceptance tests

- Emit balanced resolution and activation events for sync, async, success, failure, cancellation, and retry paths.
- Distinguish cache hits, coordinator winners, waiters, waiter failures, and later successful retries.
- Trace decorators and pre-configurations with their own semantic component paths.
- Emit cleanup events in ownership order and preserve finalizer exception aggregation.
- Apply component filters and one sampling decision per top-level resolution and typed-provider call.
- Disable a failing observer without changing activation results or suppressing application exceptions.
- Verify ordinary scopes inherit instrumentation and overlays inherit, replace, or explicitly disable it.
- Validate OpenTelemetry span topology and attributes without requiring a global provider or exporter.
- Search every event and span attribute for forbidden values, identities, owner tokens, paths, and exception messages.
- Benchmark and inspect the uninstrumented plan to prove it contains no observer branch, timing call, wrapper step, or
  event allocation.
