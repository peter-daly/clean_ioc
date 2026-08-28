# Clean IoC 2 alpha launch plan

## Positioning

> Clean IoC compiles typed Python dependency plans before startup, then resolves from an immutable runtime without rebuilding the graph.

The visual story is now stronger than a generic “DI with validation” pitch:

```text
mutable composition       build boundary          immutable runtime
ContainerBuilder     ───▶ Component plans    ───▶ Container / Scope
```

The proof points are:

1. `build()` validates every visible root without activating user code;
2. contextual generic and decorator decisions become occurrence-specific static `Component` trees;
3. resolution allocates instances and minimal activation state, not dependency graph nodes;
4. `new_scope()` is cheap, while child composition pays an explicit `ScopeBuilder.build()` cost;
5. BenchBro reports build, runtime, and Python allocation experiments separately.

## Ideal design partners

- FastAPI teams with request state and application-owned clients;
- CQRS/event systems with closed generic handlers and decorator pipelines;
- multi-tenant/plugin systems that need bounded child composition;
- test suites that build many containers and care about dynamic generic-class growth;
- library authors who want domain code free of container annotations.

Small, shallow graphs should still prefer manual wiring.

## The 20-second demo

Show a missing component failing at `build()` before constructors run. Add it, build successfully, then patch `DependencyNode` to raise if instantiated and resolve the service anyway. Finish with a FastAPI request slot:

```python
builder.declare_scope_slot(RequestContext)
container = builder.build()

scope = container.new_scope().provide(RequestContext, request_context)
scope.resolve(RequestHandler)
```

The arc is “prove once → execute frozen plan → keep requests cheap.”

## Alpha sequence

1. Publish an architecture note before a package release; explicitly label APIs experimental.
2. Ask three maintainers with generic/contextual graphs to port one composition root.
3. Ask two FastAPI maintainers to test declared request slots and teardown ownership.
4. Publish the BenchBro experiment with environment, confidence, CV, and allocation caveats.
5. Turn every unsupported graph into either a compiler rule, a documented boundary, or a deliberate rejection.

## Success measures

- three external composition roots successfully built;
- one external case exercising `ScopeBuilder`;
- one actionable report about the unified `Component` model;
- repeated benchmark direction on two machines, without a noisy hard threshold;
- 50 non-coworker stars as a discovery signal, not the product outcome.

## Likely hardening work

- aggregate all build failures instead of reporting the first;
- source locations and path-rich build diagnostics;
- cache safe activation templates across scope-overlay builds;
- formalize which provider behaviors remain runtime-only;
- replace legacy compatibility internals after the alpha API settles;
- serialize static components for tooling without serializing callables.
