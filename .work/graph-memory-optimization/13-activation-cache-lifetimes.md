# 13 — Shorten activation-cache ownership

Created: 2026-10-10\
Status: Complete — scoped KEEP accepted by coordinating review; all required checks pass\
Assignment: `/root/graph_memory_task_13`, extra-high reasoning, sequential workstream\
Recommended reasoning effort: Extra high (`xhigh`)\
Priority: Peak compiler memory\
Prerequisites: Task 06 cache/lifetime evidence; 10–11 for integration

## Recorded result

The [result](13-result.md) and [ownership inventory](13-inventory.md) record the
accepted exact-scalar weak cache, strong fallback and key-identity proof. Relative
to task 12, eight-route traced peak falls 73.146→52.137 MiB for run and
290.182→265.468 MiB for rich-rule run, with build medians 2.96% and 1.78% slower.
Retained runtime memory is unchanged; dedicated cold/steady resolution remains
close to baseline. Full CI (2,315 tests), strict docs and 68 new lifetime tests on
Python 3.11–3.14 pass. Tasks 14–18 remain queued.

## Outcome

Release intermediate execution plans when they are no longer required by the
selected graph or an observable build-time owner. An optional reuse cache should
not extend large temporary lifetimes without a defined reason.

## Work

- Map strong references from activation-template keys/values, candidate lists,
  managed adapters, selected roots, callbacks and final plans at phase boundaries.
- Separate required graph ownership from optional reuse-cache ownership. Compare
  conservative weak ownership, explicit last-use release and lightweight cache
  descriptions where each preserves the existing reuse and lifetime contract.
- Begin with task 06's exact-scalar safe subset and strong fallback for opaque
  values, containers, scalar subclasses and unknown/decorated/provider forms.
  Do not inspect arbitrary application object contents to infer safety.
- Preserve cache-key referents and identity safety when values become weak;
  recycled object IDs must not produce false cache hits. Address weakref support,
  re-entrancy, failure cleanup and overlapping ownership explicitly.
- Keep constructor activation out of compilation. Preserve callback order, derived
  values, singleton/scoped/transient ownership, cleanup and provider behaviour.
- Evaluate compatible savings in both modes; analysis evidence may still hold
  legitimate references. Do not force analysis to retain execution caches solely
  because it retains graph evidence.

## Starting evidence

There are about 31,025 activation-cache entries in the eight-route primary build,
versus 1,765 execution steps retained by the final runtime. These populations are
not interchangeable measures of reclaimable objects.

[Task 06](06-result.md) found about 29% lower traced peak for a conservative
scalar-only weak cache, with a slower build median and observed resolution timing
costs. Broad weak caching changed a later derived argument by releasing an opaque
value early, despite passing the then-current suite. Preserve every lifetime
counterexample and its exact callback outcomes as required regressions.

## Acceptance and deliverables

- Ownership/last-consumer map and a stated eligibility/fallback contract.
- Exact weakref/destructor/derived-value lifetime cases, including failed and
  rejected branches, map keys, overlays, caller-held values and both modes.
- Measurements of peak live carriers/cache entries, retained memory, build time
  and cold/steady resolution using the shared protocol. Inspect CPU/lookup costs
  independently of final graph equivalence.
- A source-integrated candidate or a documented decline; do not add savings from
  slots, table packing or other tasks before measuring the combination in 18.

Readiness gate: the conservative ownership boundary and callback-visible lifetime
contract are recorded. A smaller cache is insufficient evidence of correctness.
