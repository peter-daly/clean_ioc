# Runtime resolution profiling

Runtime profiling records what the compiled container actually resolves. It is selected at build time and is separate
from `build(profile=...)`, which measures compilation. The application decides whether to enable it at the composition
root:

```python
import os

from clean_ioc import ContainerBuilder, Instrumentation, ResolutionProfiler


class Service:
    pass


builder = ContainerBuilder()
builder.register(Service, lifespan="singleton")

enabled = os.environ.get("CLEAN_IOC_RUNTIME_PROFILE") == "1"
runtime_profiler = ResolutionProfiler(sample_durations=0.1) if enabled else None
container = builder.build(
    instrumentation=Instrumentation(runtime_profiler) if runtime_profiler is not None else None,
)

container.resolve(Service)
if runtime_profiler is not None:
    snapshot = runtime_profiler.report()
    print(snapshot.to_text())
    saved_json = snapshot.to_json()
```

Pass a `CompilationProfiler` through the independent `profile=` keyword if you also want build timing. `build_args`
remain application composition inputs; Clean IoC does not interpret a special profiling key inside them. The same
`ResolutionProfiler` continues to collect through ordinary child scopes and compatible overlay builds. An overlay must
use its parent's profiler, because it may execute steps owned by that parent.
Use a fresh profiler for a separately built container with the same graph fingerprint; the collector rejects a second
runtime for that fingerprint to keep build-local registration identities from being conflated.

The report contains exact request, activation, failure, cancellation, cache-hit, cache-miss, and coordinator-wait
counters. Timing is sampled once at each top-level resolve or provider call and that choice covers its nested DI work.
Cleanup makes a separate sampling decision when the owner closes; it does not inherit the request context. Every
duration has a sample count and a **sampled** total. The p95 is an approximate upper bound from a fixed-size
logarithmic histogram. A missing sample is not zero, and sampled totals are not estimates of whole-traffic time.

`request` timing includes dependency construction and cache waiting. A registration's `dependencies` timing covers
its dependency resolution, while `body` covers only its constructor or registered factory call, including generator or
context-manager acquisition. Decorator and pre-configuration bodies have their own records. `activation` timing
includes a registration's pre-configurations, dependencies, body, and decorators, so these nested durations overlap.
Owner cleanup timing includes its finalizers, and individual finalizer cleanup timings overlap with that owner total.
Do not add inclusive parent and child durations to claim a total. For `scope="per_call"`, target construction and
cleanup are recorded separately from the application's service method, which is excluded from DI timing.

`snapshot.records` contains compiled occurrence paths, including paths with no observed activity. A zero-count path
means **not observed during this recording**, not unreachable or unused. `snapshot.groups` aggregates by registration;
`snapshot.sharing_groups` aggregates paths using the compiled sharing references. `snapshot.ranked(by="activations")`
and `ranked(by="waits")` use exact counts, while `ranked(by="factory_time")` and
`ranked(by="slow_requests")` use sampled durations. `report()` is safe while traffic is running: completed updates
appear in the snapshot and `in_flight` states how many top-level operations had started but not finished at capture.
The returned snapshot is immutable and serializes deterministically; a later snapshot has a later capture time and
may include more observations.

When several compiled paths can consume one cached step, its activation belongs to the executable step that ran.
Cache outcomes use the actual compiled call edge, including nested dependencies, collection members, deferred
provider targets, declared resolution requests, per-call targets, and shared pre-configurations. If an edge has no
matching graph occurrence, its cache outcome is labelled `[cache caller unresolved]`; the profiler does not attribute
it to every candidate.
An async caller that waits for a shared initializer records both a cache miss and a coordinator wait.

The JSON identifies the full all-roots graph fingerprint and exposes only compiled semantic paths and registration
references. It omits configured and provided values, map keys, exception messages, runtime object IDs, and finalizer
closures. The collector retains exact counters and fixed-size duration histograms per compiled reference. It retains
no instances, arguments, traceback frames, per-request records, or unbounded event stream. A profiler failure is
marked by `incomplete` and `dropped_updates`; application resolution and cleanup continue to behave as before.
Save the JSON next to the matching graph manifest if you need to inspect it later. A report is observational evidence;
it does not change the graph, build findings, or manifest fingerprint.
