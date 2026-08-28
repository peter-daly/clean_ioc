# Launch copy

## Technical community post

### Title

Clean IoC: prove your Python dependency graph before the app starts

### Body

I maintain a typed dependency-injection container for Python, and I realized its README was selling the least interesting part: resolving constructors by type.

The new v1.25.0 release focuses on the problem I actually care about—knowing a large object graph is complete and lifecycle-safe before a cold endpoint or worker path reaches production.

```python
container.validate(CreateOrder)
print(container.explain(CreateOrder).to_text())
```

Validation is static: it does not call constructors or factories. It reports missing registrations, full dependency cycles, singletons that capture scoped/request services, and async-only paths used by sync entry points. The same model can render the selected implementations, lifespans, collections, and decorators as text or Mermaid.

Clean IoC keeps application classes framework-agnostic and adds explicit transient, per-graph, scoped, and singleton ownership. There is a FastAPI adapter with one child scope per request, plus generic handler discovery and typed decorator pipelines for CQRS/event-driven designs.

I also added a runnable FastAPI Clean Architecture example and published the microbenchmark script and results rather than making “fast” claims.

Manual wiring is still the better choice for small graphs. I would especially value feedback from people maintaining FastAPI, worker, or CQRS systems: what graph mistakes would you want a startup validator to catch?

Repository: https://github.com/peter-daly/clean_ioc

Validation docs: https://peter-daly.github.io/clean_ioc/validation/

## Short social post

Clean IoC v1.25 turns Python DI wiring into something you can prove before startup.

`container.validate()` catches missing registrations, cycles, captive request state, and sync/async mismatches—without constructing resources.

`container.explain()` renders the selected graph as text or Mermaid.

Also: coordinated concurrent lifespans, broad FastAPI compatibility, a runnable Clean Architecture example, and reproducible benchmarks.

https://github.com/peter-daly/clean_ioc

## Article outline

### Title

The dependency-injection bug hiding on your coldest endpoint

### Sections

1. A singleton accidentally captures a request-scoped unit of work.
2. Why unit tests and eager startup miss cold graph paths.
3. What can be proven from typed registrations without invoking user code.
4. Building full-path errors for missing, cyclic, captive, and async dependencies.
5. Turning the same static model into a reviewable Mermaid graph.
6. What cannot be proven: runtime behavior inside arbitrary factories and value providers.
7. When manual construction remains the clearer design.

End with the complete example and invite readers to share a graph the validator cannot yet model.
