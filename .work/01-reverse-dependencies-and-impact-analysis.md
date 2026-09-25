# 01 — Reverse dependencies and impact analysis

Status: Implemented in working tree; Sol review thread requested but not readable  
Priority: P0  
Dependencies: Existing compiled graph  
Enables: 02, 03, 05, 06, 07, 08

Implementation notes:

- Added `clean_ioc.graph_analysis` with `GraphReference`, `GraphRelationship`, `GraphIndex`, `DependencyImpact`,
  `GraphSlice`, and shared-dependency reporting.
- Added `CompiledGraph.analysis_index()`, `dependents()`, `paths_between()`, and `shared_dependencies()` facades.
- Added `clean-ioc impact` with text, JSON, and Mermaid output, service/path selection, occurrence-vs-registration
  matching, and deferred-provider inclusion.
- Documented graph analysis APIs and CLI usage in `docs/compiler-tooling.md`.
- Verification run: `uv run python -m ruff check clean_ioc tests/test_compiler_tooling.py`; `uv run pytest -q`
  (458 passed, 1 upstream FastAPI/Starlette warning).

## Outcome

Let a developer ask which components and entry points depend on a registration or an exact occurrence, inspect the
paths proving that relationship, and compare the dependencies of two entry points. Preserve the difference between
eager dependency edges, deferred provider targets, decorators, and pre-configurations.

Illustrative output:

```text
PaymentGateway
  Direct consumers: Checkout, RefundOrder
  Affected entry points: PlaceOrder, CancelOrder
  Boundaries reached from: orders, refunds
  Deferred consumer: RetryWorker → Provider[PaymentGateway]
```

## Current foundation

- `CompiledGraph.walk()`, `GraphVisit`, `component_at_path()`, and manifests provide forward traversal and paths.
- `Component.id` identifies a registration; `occurrence_id` identifies a use in a particular graph.
- Graph roots include architectural roots; default rendering can focus on marked entry points.
- Shared pre-configurations, cloned provider-root metadata, and anchored singleton steps mean the representation is not
  safely reducible to one node per type or one unique path per executable step.

Primary integration points: `clean_ioc/tooling.py`, `components.py`, `_graph_roots()` and `_finalize_plan()` in
`container.py`, `cli.py`, and `tests/test_compiler_tooling.py`.

## Proposed model and API

Add `clean_ioc.graph_analysis` for shared analysis types and algorithms; keep `CompiledGraph` methods as thin facades.

- `GraphReference`: graph-local occurrence reference plus deterministic semantic path. Export paths, not UUIDs.
- `GraphRelationship`: parent/child references, relationship kind, argument, order, and eager/deferred classification.
- `GraphIndex`: occurrence lookup, registration-to-occurrences mapping, incoming/outgoing edges, root membership, and
  source boundary. Build it lazily and cache only immutable indexes associated with one compiled graph.
- `DependencyImpact`: selected targets, direct consumers, affected roots/entry points, and path-query facilities.
- `GraphSlice`: bounded subgraph projection with explicit truncation metadata.

Proposed methods:

```python
impact = graph.dependents(component, match="occurrence")
impact = graph.dependents(component, match="registration", include_deferred=True)
slice = graph.paths_between(root_component, dependency_component, max_paths=100)
shared = graph.shared_dependencies(first_root, second_root, match="registration")
```

Type/name selectors may be convenience overloads but must report ambiguous selection instead of silently collapsing
several registrations. Registration matching includes every occurrence of that exact registration, not every object
with the same service type. Do not rerun arbitrary component filters for these queries.

## Implementation stages

### 1. Define identity and relationship semantics

- [ ] Extract/reuse deterministic path construction so manifests, queries, and future telemetry use the same rules.
- [ ] Preserve all paths to a shared occurrence; a record ID alone must not erase incoming relationships.
- [ ] Enumerate dependency, decorator, pre-configuration, deferred-target, and declared-resolution edges explicitly.
- [ ] Define direct consumers as graph-adjacent relationships, with an optional logical-consumer projection that skips
  synthetic provider/collection nodes while retaining the skipped path as evidence.
- [ ] Index all architectural roots once. Apply entry-point-focused presentation only when producing a report.

### 2. Implement reverse and intersection queries

- [ ] Traverse incoming edges for exact occurrence queries; expand target registrations before registration-wide queries.
- [ ] Calculate eager-only reachability separately from reachability that crosses a provider boundary.
- [ ] Return root membership and one witness path cheaply; enumerate all paths only on explicit request.
- [ ] Bound path enumeration and subgraph size. Report `truncated`, returned count, and configured limit; never imply a
  truncated list is complete. Avoid exponential work in default impact summaries.
- [ ] Support shared-dependency intersections without counting duplicate occurrence expansion as extra registrations.

### 3. Expose reports and CLI

- [ ] Add deterministic text/JSON reports and Mermaid slices, with entry points and selected targets highlighted.
- [ ] Add `clean-ioc impact TARGET SERVICE --match registration` and `--path` for exact occurrence selection; support
  name selection, deferred inclusion, all-roots selection, output path, and path limits.
- [ ] Reject missing/ambiguous targets as usage/query errors. An empty dependent set is a valid result.
- [ ] Keep impact analysis informational; do not make ordinary high fan-in an automatic build failure.

### 4. Documentation and performance

- [ ] Add recipes for replacing an adapter, finding shared infrastructure, and inspecting a boundary crossing.
- [ ] Measure index construction and bounded queries on wide, deep, and shared graphs. Separate index cost from query
  cost and verify no effect on uninstrumented resolution or ordinary scope creation.

## Verification

Test diamonds, multiple same-type registrations, named roots, default and all-root views, shared initializers,
decorator dependencies, providers/collections/maps, private boundaries, and anchored overlays. Verify a registration
query finds all intended occurrences while an occurrence query stays path-specific. Equivalent builds must give equal
serialized reports despite new registration UUIDs. Bounded queries must terminate with honest truncation metadata.
Use callbacks that raise if invoked after build to prove inspection does not execute composition code.

## Acceptance criteria

- A selected registration can list every affected compiled root and marked entry point with a witness path.
- Eager and deferred reachability are distinguishable and boundaries do not disappear from projections.
- All-path queries are bounded; ordinary summaries do not enumerate all paths.
- Existing manifests and runtime execution remain unchanged.
