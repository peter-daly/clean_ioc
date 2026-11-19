# 08 — Diagnostics, explanations and runtime profiling

Created: 2026-10-09\
Status: Not ready — optional capabilities and metadata contract need decisions\
Assignment: Unassigned\
Prerequisites: Task 02's capability matrix; coordinate payload design with 06

## Outcome

Keep useful load/resolution failures and optional runtime profiling without
recreating the full explanation graph in a reduced loaded container. Preserve
existing meanings of build diagnostics, explanation metadata and instrumentation.

## Readiness and remaining decisions

- Choose which full/reduced metadata and instrumentation combinations the first
  delivery supports. Decide whether a profiling-ready artifact is required or
  profiling can be attached to any loaded artifact.
- Define the minimum profiling catalogue and correlation keys. Decide whether it
  is embedded, an optional sidecar or omitted when profiling is not requested.
- Decide where full build explanations/reports live and what a reduced runtime
  exposes when those reports are absent. Do not imply a full graph can be rebuilt
  from compact labels.
- Specify the minimum origins/paths needed for actionable load, provision and
  resolution errors and their memory cost.

The current `_observe_plan` requires `plan.compiled_graph`. Normal reduced builds
can instrument before stripping that graph; loading an already reduced artifact
cannot simply reuse that sequence. Resolve this explicitly before implementation.

## Work

1. Inventory profiling/report consumers and classify each required field as
   runtime execution data, compact correlation data or full explanation data.
   Preserve metadata actually used by runtime filters and component relationships.
2. Design a compact catalogue using the existing profiler's concepts for paths,
   sharing/ownership, activation and cleanup. Keep collectors, recordings and
   binding identities fresh per loaded container through task 04.
3. Reconnect observer steps/hooks using frozen information and the agreed load
   options. Do not reconstruct the graph, invoke analysis callbacks or silently
   retain all compiler metadata to enable profiling.
4. Define optional full reports and disabled-capability errors. Build diagnostics
   remain compile-time evidence; a loaded container must not claim it has rerun
   validation or collected build evidence it does not possess.
5. Preserve public report redaction and existing unversioned beta conventions.
   Do not merge configured values or runtime measurements into structural graph
   fingerprints. Coordinate artifact identity separately with task 06.
6. Measure retained/peak memory and activation overhead for each supported mode.
   Uninstrumented resolution must not gain reporting work merely because the
   container came from an artifact.

## Verification and acceptance

- [ ] A supported-mode table distinguishes build diagnostics, explanations and
  runtime instrumentation and gives clear errors for unavailable capabilities.
- [ ] Loaded profiling records correlate with the same logical activations,
  sharing and cleanup as normal compilation for supported features.
- [ ] Reduced artifacts never regenerate full graphs to answer reporting calls.
- [ ] Repeated loads have independent collectors and observations; ordinary
  uninstrumented resolution retains its existing execution path.
- [ ] Mode-by-mode memory measurements show the cost of optional metadata and
  preserve the reduced-mode benefit with documented limits.

## Starting points

- `_observe_plan` and observed runtime steps in
  [container.py](../../clean_ioc/container.py).
- [Runtime profiling documentation](../../docs/runtime-profiling.md),
  [profiler tests](../../tests/test_resolution_profiler.py) and
  [reduced-runtime tests](../../tests/test_optional_explanation_metadata.py).
- [Explanation metadata inventory](../graph-memory-optimization/05-inventory.md)
  and [result](../graph-memory-optimization/05-result.md).
