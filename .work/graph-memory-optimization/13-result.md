# Task 13 result — conservative activation-cache ownership

Task 13 is complete. Scoped decision: **KEEP**, with coordinating review and all
required local checks passed. Task 13 uses its recorded extra-high effort. No commit,
version bump, push, release or production action is included.

## Change and safety boundary

The compiler's optional activation cache now weakly owns only completed, exact
known registration-step closures containing exact scalar leaves. Opaque values,
containers, scalar subclasses, providers/maps, decorators/configurations and
unknown execution forms preserve their strong ownership. Literal, sequence and
unknown requested-type key grammars also remain strong. No public build flag or
capability changes. No constructors run during compilation, and no callback is
skipped or replayed.

The [ownership inventory](13-inventory.md) records required owners, last consumers,
key identity guards, metadata/factory owners, fallback policy, occurrence and
profiling attribution, re-entrancy and failure cleanup. There is no persistent
eligibility memo, runtime traversal, slots change, draft/index/snapshot change or
artifact representation change. Selected roots, invariant subplans, managed
adapters and inherited runtimes retain their required strong ownership.

A single native dictionary preserves fallback lookup behavior. Weak entry removal
uses only library-owned key shapes and exact identity-based type-key branches.
Callbacks retain the cache weakly and verify entry identity before deletion, so
an old callback cannot delete a replacement. Application values are not hashed,
compared or inspected to classify eligibility.

Two review findings narrowed the historical task 06 candidate:

1. `type(value) in (...)` can invoke application metaclass equality; it is not an
   exact-type guarantee. All carrier/scalar whitelist checks now use identity.
   The incomplete initial timing log is preserved as superseded evidence.
2. Inert leaves alone are insufficient for mixed-dictionary callback removal.
   A public Literal contract can change its literal value type's module label
   from an application string subclass to an exact string between rejections.
   Removal then compares against an older strong key and changes observable
   equality timing. The public [probe](evidence/13/literal-key-probe.py) returns
   **False** with strong ownership, **True** with the superseded candidate, and
   **False** with the final grammar restriction. The superseded complete matrix
   is preserved separately and is not acceptance evidence.

Rejected-then-selected equal-key tests also prove the attribution boundary:
strong control hits, weak candidate misses, yet selected occurrence/profile paths,
activation/finalization, scope ownership and callback order agree in both public
modes for all four lifetimes. Opaque rejected values and map keys preserve the
original later callback result in all sixteen historical lifetime cases.

## Final build and memory measurements

The accepted task 12 AFTER samples are the BEFORE control. All eleven accepted
production/fixture/harness hashes matched before editing; full starting identity,
working diff and relevant source copies are saved in
[before-identity.json](evidence/13/before-identity.json). Final AFTER uses the same
unchanged shared public-mode harness, three fresh untraced processes and three
separate traced processes per control, serially with no competing tests or
benchmarks. Python 3.14.4, macOS ARM64; no retained caller builder or snapshots.
Traces cover fixture import/composition/build. Traced retained memory is after
collection; traced peak and RSS are distinct measurements.

The rich run control installs an arbitrary mandatory rule asserting that complete
temporary diagnostics are available. Analysis retains its complete graph and
composition. Eight routes exercise ordinary and rich run; two bound analysis cost.
Values are medians computed directly from the raw sample rows in
[task 12 AFTER](evidence/12/after.json) and [final task 13 AFTER](evidence/13/after.json),
with exact medians and separate ranges in
[comparison-summary.json](evidence/13/comparison-summary.json).
**Task 12 accepted baseline → final task 13 candidate**:

| Control | Build s | Shared resolve workload ms | Retained traced MiB | Peak traced MiB | Current RSS MiB | Peak RSS MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Run, 8 routes | 5.712 → 5.881 | 14.294 → 14.041 | 3.103 → 3.103 | 73.146 → 52.137 | 132.438 → 106.734 | 132.438 → 106.734 |
| Rich-rule run, 8 routes | 8.483 → 8.634 | 14.906 → 15.001 | 3.102 → 3.102 | 290.182 → 265.468 | 350.656 → 325.828 | 355.531 → 328.828 |
| Analysis, 2 routes | 0.282 → 0.293 | 2.659 → 2.747 | 6.482 → 6.482 | 7.762 → 7.627 | 49.391 → 49.359 | 49.391 → 49.359 |

Run peak falls **28.72%**, with **2.96% slower** build. Normal build ranges are
5.698–5.719 versus 5.871–5.997 seconds. Rich-rule run peak falls **8.52%**, with
**1.78% slower** build (8.478–8.572 versus 8.580–8.716 seconds). Analysis peak
falls **1.74%**, with **4.00% slower** build (0.281–0.284 versus 0.287–0.296 seconds).
The small analysis RSS difference is not a meaningful saving. Successful-runtime
retention is unchanged within a few hundred bytes. This trades compiler CPU for
lower live peak, not lower construction count or faster resolution.

Bark-like arbitrary mandatory rules use the rich path: do not apply the ordinary
run percentage to them. These results are relative to task 12's accepted source;
do not add standalone savings from earlier tasks. Task 18 must measure the actual
combined implementation.

Traced peak ranges are independent of those normal-process timing ranges:

| Control | BEFORE traced peak MiB, min–max | AFTER traced peak MiB, min–max |
| --- | ---: | ---: |
| Run | 73.146258–73.146411 | 52.136708–52.137168 |
| Rich-rule run | 290.181683–290.182601 | 265.467848–265.468532 |
| Analysis | 7.761981–7.762072 | 7.626232–7.626953 |

All final samples preserve validated fixture results, template/derivation callback
counts, activation counts, selected registrations, retained graph inventories and
execution-step populations. Eight-route run retains 8,982 physical records, 1,765
execution steps and 51 selected registrations. The source and result cross-check
is recorded in [evidence-validation.json](evidence/13/evidence-validation.json).

## Cold and steady resolution

The separate [resolution harness](evidence/13/resolution.py) builds outside the
timer and resolves eight complete workloads in each fresh process: the first is
cold and the next seven form that process's steady median. It compares the final
cache with the original native strong dictionary, three fresh processes for each
policy/control, serially. Cleanup and validation occur outside each timer.
The 18 processes therefore cover 144 validated workloads. These absolute times
exclude the shared memory harness's collection boundary and must not be compared
directly to its resolve column.

Medians across processes, in milliseconds, **strong control → final cache**:

| Control | Cold wall | Steady wall | Cold process CPU | Steady process CPU |
| --- | ---: | ---: | ---: | ---: |
| Run | 10.006 → 10.041 | 9.740 → 9.767 | 10.010 → 10.046 | 9.740 → 9.764 |
| Rich-rule run | 10.156 → 10.274 | 9.736 → 9.755 | 10.165 → 10.279 | 9.739 → 9.759 |
| Analysis | 2.096 → 2.072 | 1.900 → 1.896 | 2.103 → 2.075 | 1.900 → 1.896 |

Cold and per-process steady ranges overlap in all three controls. Run cold ranges
are 9.980–10.009 versus 9.978–10.490 ms; steady ranges are 9.729–9.786 versus
9.762–9.787 ms. Full ranges and exact medians are in
[resolution-summary.json](evidence/13/resolution-summary.json), with all samples in
[resolution.json](evidence/13/resolution.json). The historical approximately 16%
resolution penalty is not reproduced. No resolution speedup is claimed, and the
implementation adds no runtime cache or closure traversal.

## Created, live and retained populations

The separate intrusive [census](evidence/13/ownership-census.py) records constructor
calls, per-class maximum live counts, and counts immediately after build. It is
excluded from latency and byte measurements. Both eight-route controls produce
the same census: primary admissions/misses remain **31,025**, hits **25,081**;
peak live cache entries fall **31,025 → 635**, and entries at compiler release
**31,025 → 617**. The final fixture's admitted primary entries are all weak;
opaque fallback is exercised by the lifetime tests, not by this scalar fixture.
Analysis primary admissions/misses remain 327 and hits 1,906; peak live entries
fall 327 → 103 and entries at compiler release 327 → 101.

Eight-route populations, **strong control → final cache**:

| Carrier | Constructed, unchanged | Maximum live | Retained after build, unchanged |
| --- | ---: | ---: | ---: |
| Value step | 31,156 | 31,026 → 637 | 618 |
| Compiled dependency | 61,220 | 35,228 → 1,740 | 1,740 |
| Singleton registration step | 1,572 | 1,570 → 227 | 226 |
| Transient registration step | 51,400 | 26,310 → 331 | 326 |
| Scoped registration step | 3,736 | 3,274 → 200 | 193 |
| Provider-map step | 32 | 32 → 32 | 32 |

Per-class maxima occur at potentially different times and must not be summed.
All counted live carriers reach zero after runtime teardown. Analysis construction
counts and after-build retention also match; its value/dependency maximum-live
counts fall 322 → 98 and 536 → 272. Full before/after census files cover every
control. This is shorter temporary ownership, not reduced construction churn.

The existing profiler label `unique activation templates` counts cache admissions
or generations. Equal keys can be recreated after eviction, so that label is not
structural uniqueness or simultaneous live entries. The public compiler-tooling
documentation now explains this interpretation.

## CPU and traversal costs

One separate cProfile build per policy/control attributes costs; these instrumented
runs are descriptive and do not replace the normal-process timing matrix.
Eight-route final profiles perform 56,300 cache lookups, 31,219 insertions and
eligibility walks, and 30,480 removal callbacks across all compilation phases.
Analysis performs 2,259 lookups, 353 insertions/walks and 232 removals.

For ordinary run, scalar-closure walks take 0.081 seconds own / 0.131 cumulative;
key checks take 0.137 / 0.226; lookup 0.020 / 0.061; insertion 0.032 / 0.389;
removal 0.009 / 0.012. Rich run has essentially the same traversal counts and
0.388 seconds cumulative insertion cost. Analysis insertion is 0.005 seconds
cumulative. Nested cumulative costs overlap and must not be added. The cost of
repeated closure/key walks is accepted for the measured peak reduction; a new
memo ownership system is not bundled. Raw before/after profile files and
[cpu-profile.py](evidence/13/cpu-profile.py) are retained.

## Verification and evidence identity

- [Full CI](evidence/13/make-ci.txt): Ruff lint/format, type checking, **2,315 tests**,
  executable documentation and BenchBro discovery pass on Python 3.14.4.
- [Strict documentation](evidence/13/docs-strict.txt) passes.
- The **68 new lifetime tests** independently pass on
  [Python 3.11](evidence/13/python311.txt), [3.12](evidence/13/python312.txt) and
  [3.13](evidence/13/python313.txt), as well as the full 3.14 suite.
- The original 16 opaque-value/map-key/scalar-subclass counterexamples remain
  explicit regressions. Public modes, failures, rejected branches, overlays,
  caller-held values, custom metaclasses/key equality, cleanup/profile attribution,
  stale weak callbacks and re-entrant success/failure builds are covered.
- Existing artifact round trips pass in the full suite; artifact representation
  is untouched. The previously recorded Python 3.15-development alias TypeError
  remains outside these supported-version checks; no assertion was relaxed.
- `git diff --check` passes. No production code changed after the final matrix.
  CI required type-only annotations/ignores in the four task-local measurement
  scripts; their exact measured forms are preserved as `*.py.measured.txt`.
  The shared matrix harness and production source are unchanged.

[accepted-source.json](evidence/13/accepted-source.json) records the final source,
fixture/harness hashes, interpreter, settings and evidence identity. The
[task-local source patch](evidence/13/task13-source.patch) is relative to saved
accepted task 12 source and contains only this task's production/test/documentation
changes. The complete initial shared dirty diff remains preserved. Superseded
metaclass/literal candidates are not mixed with accepted samples.

## Handoff to task 14

Task 14 may use final task 13 AFTER as its BEFORE only after validating the accepted
source hashes, fixture/harness/settings and interpreter. Preserve all earlier
uncommitted work. Target mutable draft definitions under the same task 10/11
public-mode/evidence contracts; do not widen this cache eligibility or promote
parked pre-compilation work. Registration/layer/requested-type/dependency identity
owners and occurrence/profiling attribution remain required even when optional
cache entries disappear. The opaque strong fallback and mutable-literal regression
are mandatory boundaries for any later representation change.

Task 13's peak benefit is scope-dependent: rich mandatory-rule builds show the
smaller 8.52% saving and unchanged retained runtime size. Keep the approximately
1.8–4.0% build CPU/time tradeoff explicit and measure the combined implementation
in task 18. Tasks 14–18 remain queued; this agent has not begun task 14. No commit,
version change, push, release or production action was performed.
