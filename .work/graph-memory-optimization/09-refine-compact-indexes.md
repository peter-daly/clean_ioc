# 09 — Refine compact indexes and verify dictionary compatibility

Created: 2026-10-09\
Status: Complete — corrected isolated prototype retained\
Assignment: GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning\
Agent: `/root/graph_memory_task_09`\
Prerequisites: Task 08's completed investigation and native-delegation feasibility probe\
Production readiness: Scoped verification complete; ready for implementation review, not production adoption

## Outcome and scope

Integrate the fixes for task 08's six mapping counterexamples into one isolated
compact-index candidate, choose a bounded small/sparse fallback policy, and establish
whether the corrected candidate retains worthwhile memory savings. Produce a
retain, refine or drop recommendation with an explicit production-readiness decision.

This task follows the [task 08 result](08-result.md),
[reader/contract inventory](08-inventory.md) and [shared rules](README.md).
The work is prototype refinement and verification; leave shared production sources
unchanged at completion. Do not commit, push, combine cache/slots optimizations or
expand the parked pre-compilation feature work. Preserve all task 08 evidence and
write new `09-*` probes/results. The maintainer assigned GPT-6.1 Sol with medium
reasoning on 2026-10-09.

## Why a follow-up is needed

Task 08's measured candidate lowers reduced-mode traced build peak from
72.844 to 67.851 MiB and process RSS from 130.438 to 119.734 MiB, with no established
build-time change. Full-mode retained Python memory falls from 38.432 to 33.523 MiB.
These local synthetic measurements are historical context, not the new baseline.

All 2,132 existing tests and 18 artifact tests pass, but six stronger custom-hash
checks fail. Inherited mapping helpers hash keys again where a native dictionary
uses fewer calls or reuses stored hashes. This can raise when a dictionary succeeds:

| Operation | Observed incompatibility |
| --- | --- |
| `setdefault` | Two hash calls instead of one |
| `pop` | Two hash calls instead of one |
| `copy` | Rehashes keys rather than reusing stored hashes |
| Equality | Rehashes existing keys |
| `update` | Rehashes keys copied from another dictionary |
| Read-only proxy equality | Rehashes an equivalent custom key in the other dictionary, even when the index itself contains only integers |

The [native-delegation feasibility probe](evidence/08-hash-counterexamples.py)
passes all six cases, but was never installed in the compiler/artifact candidate
or its repeated measurements. The maps are private graph/plan fields; document
their actual observable contract without inventing a public origin-map API.

Task 08 also found tiny-map overhead, 15.3% additional shallow storage for
100,000 sparse-only entries, permanent loss of compact storage after promotion,
and roughly 8% longer full-artifact loading. These costs need an explicit decision.

## Work

### 1. Integrate native dictionary behaviour

- Integrate the feasibility fix into the isolated compiler and codec candidate,
  preserving the exact-integer insert/update/get fast path. Ensure that general
  operations delegate directly after promotion; inherited generic helpers must
  not reintroduce extra hashing around a native backing dictionary.
- Audit equality in both directions, proxy equality, copies, views, reverse
  iteration, unions and generic mutable operations, including `setdefault`,
  `pop`, `popitem`, `update` and `clear`. Cover compact and already-promoted states,
  missing/default paths, custom equality/hash behaviour and exception outcomes.
- Preserve key/value identity, insertion order, live wrappers, snapshot copies,
  iterator invalidation and deletion/reinsertion behaviour. Existing wrappers
  must continue to share the same backing object through transitions.
- Retain the six original counterexamples and compare native outcomes/hash counts.
  Extend focused tests for newly audited paths. Integer-only compiler writes are
  not a reason to dismiss the read-only equality failure. Any narrower internal
  API requires a documented, compatible adapter boundary and a readiness decision.

### 2. Select and measure a small/sparse fallback policy

- Compare ordinary dictionary storage against compact storage for empty/tiny,
  dense, gapped, reverse-inserted, negative-only, huge-ID and mixed indexes.
  Choose thresholds from measured storage and construction costs, not dense-case
  arithmetic alone. Record any residual small-map carrier overhead explicitly.
- Bound array growth, fallback storage and transition frequency. Exercise growth
  across thresholds, changes in density and deletion. Avoid repeated conversions,
  retained duplicate dictionaries or a whole-map conversion at graph completion.
- Measure transition/promotion peak memory and time as well as steady storage.
  Preserve graph-local namespaces, occurrence IDs and captured provenance; count
  borrowed keys and shared origin values once. Document which operations permanently
  relinquish compact storage and why the resulting tradeoff is acceptable or unresolved.

### 3. Verify the integrated artifact and compiler paths

- Adapt task 08's direct compact codec to the final candidate, preserving memoized
  backing identity and shared proxies through compact, fallback and promoted states.
  Regenerate source-coupled experimental artifacts and record schema/source checks;
  do not add a production format or migrations.
- Recheck all former artifact failures, full/reduced round trips, malformed or
  unsupported payload rejection and atomic publication. Export/decode must not
  retain duplicate full dictionaries merely to make serialization pass.
- Verify graph facts, source attribution, fingerprints, callback order/counts,
  failed-build witnesses and task 06's lifetime counterexamples. Cover providers,
  maps, scopes/overlays, aliases/generics, boundaries, warmup, diagnostics, profiling
  and cleanup through existing and focused tests where affected.
- Run the full suite and applicable repository checks against the integrated
  candidate. Repeat focused supported-Python checks and state unavailable coverage.
  A passing standalone helper does not count as integrated verification.

## Measurement

- Compare a fresh same-source baseline with the final corrected candidate using
  the unchanged rich eight-route fixture. Record exact source/probe hashes,
  interpreter, architecture, build options, caller ownership and process IDs.
- Use at least five fresh normal and three separate traced processes for compiler
  comparisons in reduced and full modes. Run serially without competing workloads;
  prepare transformed source/bytecode outside measured processes. Keep preliminary
  candidates separate if executable behaviour changes during investigation.
- Report retained Python memory after collection, traced peak, current/peak RSS,
  build/cold-resolution time and graph/step counts separately. Include bounded
  diagnostics/failure controls and storage/lookup/inspection screens for affected
  paths. Avoid census/view creation promoting indexes before the intended observation.
- Run three normal and three separately traced export/load processes per candidate
  and full/reduced mode. Measure artifact cold resolution before census or inspection.
  Report size, export/load time, retained/peak allocations and cumulative RSS, with
  conversion/promotion costs identified separately.
- Reassess task 08's lookup and full-load penalties and whether savings survive
  native delegation/fallback. Do not add independent cache/slots savings, mix old
  and new baselines, or infer production capacity from this synthetic workload.

## Deliverables and acceptance

- [x] All six original counterexamples pass in the integrated candidate, alongside
  the completed operation audit and documented mapping boundary.
- [x] A tested small/sparse policy bounds growth and transition costs; remaining
  memory/time regressions have explicit retain/refine/drop decisions.
- [x] Full/reduced artifacts preserve backing identity and compiler behaviour;
  applicable semantic, lifetime, full-suite and repository checks pass.
- [x] Repeated measurements describe the final corrected candidate and establish
  its net memory benefit and timing costs, including artifact loading and promotion.
- [x] `09-result.md` records the recommendation, production readiness and remaining
  limitations; reproducible `09-*` evidence preserves all earlier results.
- [x] Update both work indexes and leave shared production sources unchanged.
  Unresolved correctness or measurement gaps mean not ready; dropping the proposal
  is acceptable if compatibility costs erase its benefit.

## Recorded outcome

[Result](09-result.md) and [boundary inventory](09-inventory.md): all six original
counterexamples, 103 operation/codec checks, 2,132 tests, 16 lifetime cases and
focused supported-Python checks pass. The final 104-process matrix retains
~4.96 MiB reduced peak/full retention savings. Sparse/tiny maps pay 72-byte
carrier overhead; full artifact export/load medians rise ~13%, and narrow dense
lookups remain ~3× native. RETAIN the corrected prototype for implementation
review; production adoption is not approved. Shared production sources and all
prior evidence remain unchanged. Unmodified repository lint has one preserved
Task 08 E501; the narrowly exempted rerun passes.
