# Declared warm-up plans

Warm-up plans declare singleton services to initialize during application startup.
Build selects and validates their frozen targets without constructing them. The
application explicitly runs one named plan after build. Successful initialization
does not prove connectivity, health, readiness, or deferred provider acquisition.

```python
from collections.abc import Iterator
from clean_ioc import ContainerBuilder, WarmupPlan, WarmupTarget

class Pool:
    pass

events = []
def pool() -> Iterator[Pool]:
    events.append("open")
    try:
        yield Pool()
    finally:
        events.append("close")

builder = ContainerBuilder()
builder.register(Pool, factory=pool, lifespan="singleton")
builder.add_warmup_plan(WarmupPlan("startup", [WarmupTarget(Pool)]))
with builder.build() as container:
    assert events == []
    container.warmup("startup").raise_for_errors()
    first = container.resolve(Pool)
    container.warmup("startup").raise_for_errors()
    assert container.resolve(Pool) is first
    assert events == ["open"]
assert events == ["open", "close"]
```

`WarmupPlan` captures the target iterable into an immutable ordered tuple.
`WarmupTarget` requires a closed service key and an optional synchronous `filter`.
The default filter selects unnamed registrations. Use
`WarmupTarget(Client, filter=cf.with_name("primary"))` or an ID filter for named
selection. Each target must select exactly one visible resolvable singleton after
normal fallback and nearest overlay-layer selection. Multiple matching registrations
in that layer are ambiguous. Collections, slots, dependency-only registrations,
provider handles and non-singleton targets cannot be warmed directly.

Closed generic requests create explicit compilation demand, including structural
patterns. Aliases, exposures, decorators, pre-configurations, return annotations and
ordinary ownership rules apply. Targets are captured once; runtime never invokes
selection filters. Repeated requests selecting the same singleton in one plan fail
build. Sharing a target between distinct plans is legal.

`ContainerBuilder` and `ScopeBuilder` support declarations. Visible names must be
nonempty and unique across inherited layers. After a failed build,
`remove_warmup_plan(name)` removes local declarations before repairing the builder;
it cannot remove inherited plans. Successful builders remain single use.
An overlay recompiles inherited intent against its visible composition. Parent
singletons retain parent ownership; overlay replacements belong to the overlay.
Ordinary child scopes reuse the frozen selections.

Targets execute sequentially in declaration order, each with a fresh normal
resolution context. Internal dependency concurrency and ordering remain unchanged.
Ordinary exceptions are aggregated and later targets still execute. Successful
resources remain owned and cached; failure reporting introduces no rollback.
Failed initializers can retry on a later explicit run under ordinary singleton
rules. Concurrent warm-up and ordinary resolution share the same coordinator.

```python
from clean_ioc import ContainerBuilder, WarmupError, WarmupPlan, WarmupTarget

class Broken:
    pass
class Successful:
    pass

def fail():
    raise RuntimeError("private connection details")

builder = ContainerBuilder()
builder.register(Broken, factory=fail, lifespan="singleton")
builder.register(Successful, lifespan="singleton")
builder.add_warmup_plan(WarmupPlan("startup", [WarmupTarget(Broken), WarmupTarget(Successful)]))
try:
    with builder.build() as container:
        report = container.warmup("startup")
        assert [result.status for result in report.results] == ["failed", "succeeded"]
        assert "private connection details" not in report.to_json()
        report.raise_for_errors()
except WarmupError as error:
    assert error.report.name == "startup"
    # Escaping the owning context shuts down acquired resources normally.
```

Use `await warmup_async(name)` whenever activation or eager cleanup needs async.
Sync warm-up preflights the whole plan and executes nothing if any target needs
async. Every result then has `not_executed` status; async targets carry the
`warmup-requires-async` finding. Async runs accept both sync and async targets.

```python
import asyncio
from collections.abc import AsyncIterator
from clean_ioc import ContainerBuilder, WarmupPlan, WarmupTarget

class Client:
    pass

events = []
async def client() -> AsyncIterator[Client]:
    events.append("open")
    try:
        yield Client()
    finally:
        events.append("close")

async def main():
    builder = ContainerBuilder()
    builder.register(Client, factory=client, lifespan="singleton")
    builder.add_warmup_plan(WarmupPlan("startup", [WarmupTarget(Client)]))
    async with builder.build() as container:
        preflight = container.warmup("startup")
        assert not preflight.is_valid and events == []
        (await container.warmup_async("startup")).raise_for_errors()
        assert events == ["open"]
    assert events == ["open", "close"]

asyncio.run(main())
```

Cancellation, `KeyboardInterrupt`, and other control signals propagate and stop
later attempts. Keep the relevant owners open while warming and using services;
warm-up does not extend their lifetime. Unknown plan names raise `KeyError`; closed
scopes raise `ScopeClosedError` before execution.

`container.warmup_plans` and `container.graph.warmup_plans` expose immutable intent
records, selected semantic paths, sources and async requirements without activation.
Default manifests and fingerprints exclude this declaration sidecar. A closed
request that adds a specialization may change the compiled graph.
Build, validation, CLI graph/check/activation commands, semantic diff and build
matrices never execute plans. Warm-up intent does not mark entry points, so existing
`unreachable-component` warnings may remain when a target is outside entry-point
reachability. Static activation scenarios remain hypothetical.

`WarmupReport` is a detached immutable observation with plan name, matching full
graph fingerprint, ordered target identities, paths, sources and outcomes.
`to_text()`, `to_json()` and `to_sarif()` render deterministically. `assert_valid()`
raises an assertion containing SARIF findings; `raise_for_errors()` raises
`WarmupError` containing the safe report. Neither helper retries or closes owners.
Failure messages are fixed and exception types qualified. Exception objects,
messages, tracebacks, resources, configured values and runtime IDs are omitted.
Reports do not infer nested throw sites or distinguish cached successes as
“already warm”. The opt-in runtime profiler observes requests, activation, caches,
waits and eventual cleanup through its existing identities and counters.
