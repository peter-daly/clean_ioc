# 04 — Reuse subplans with unmatched decorators

Created: 2026-11-18  
Status: Declined — implementation stashed \
Priority: P2 — recommended; not a release blocker  
Blocked by: None — can start immediately  
Assignment: GPT-6.2 Sol (`gpt-6.2-sol`), high reasoning — `/root/v2_item04`

## Outcome

Preserve invariant subtree reuse when generated decorators cannot target the subtree. Keep ordinary compilation whenever callbacks or contextual behavior make reuse unsafe.

## Review evidence

`_Compiler._compile_decorators` increments `_subplan_unsafe_epoch` whenever generated decorators exist, even when all pure service selectors reject the component and no applicability callback runs. This prevents unrelated shared infrastructure from entering the existing invariant-subplan cache.

A process-only prototype delayed the unsafe marker until definitions reached applicability evaluation, while retaining conservative behavior whenever explanation or diagnostic evidence was captured. On the existing four-route graph-memory fixture, five alternating baseline/candidate runs produced median build times of **525.9 → 346.0 ms**, approximately 34% lower.

One fresh-process allocation sample per variant measured peak traced allocations of **6,907,743 → 6,566,329 bytes**, and retained allocations after GC of **1,180,613 → 1,131,229 bytes**. These samples are exploratory, not memory guarantees or process-RSS measurements.

Retained physical graph records increased **3,198 → 3,220**. Existing cache hits clone fresh inspection occurrences but return the original executable step, retaining nine additional `RouteDependency` occurrences, two `Policy` occurrences, and eleven associated values. Investigate and explain this tradeoff rather than requiring unchanged record counts.

Sixty-eight focused tests passed with the prototype. Full fixture execution also preserved template call counts, 48 workers, 3,024 transient tree objects, singleton identity, and 14 managed scopes. This was exploratory verification, not production validation. Evidence resides in `.benchbro/v2-perf-review/compiler_decorator_*`.

## Implementation guardrails

Distinguish pure selector rejection from a rejected applicability callback: the latter must still execute per occurrence. Preserve opaque callbacks and existing hashing/equality contracts; do not infer purity from names or cache arbitrary user behavior. Maintain selection order, boundaries, ownership, cleanup, occurrence inspection, diagnostics, and profiling semantics.

Keep reuse compiler-local. Preserve its cycle, retention-context, failed-compilation, and unsafe-descendant protections. Do not introduce a cross-build cache or silently suppress explanation evidence.

## Acceptance criteria

- [x] Unrelated generated decorators no longer prevent otherwise-safe subtree reuse.
- [x] Matching or callback-bearing alternatives retain ordinary evaluation and callback counts.
- [ ] Build and verify remain behaviorally consistent, including diagnostics and failure paths.
- [x] Additional retained records are characterized and justified without weakening graph semantics.
- [ ] Focused regressions and the [common validation criteria](README.md) pass.

## Validation and measurement

Add coverage for unmatched selectors, matched-but-rejected callbacks, contextual descendants, boundaries, and failures. Re-run invariant-subplan, decorator-template, graph-memory, and diagnostics coverage. Repeat alternating timing runs and separate fresh-process allocation samples, validating fixture identities and callback counts each time. Report retained records alongside bytes; do not impose a fixed percentage performance gate.

### Implementation

Execution builds reuse existing compiler-local subplans when each visible
generated selector is provably unrelated. Identity-only service groups and
unrelated plain class hierarchies qualify. Applicability and position callbacks,
projection, candidate ordering and evidence collection use the existing path.
Verification keeps per-occurrence rejection evidence.

The compiler also checks the inputs that a hit would skip. An opaque registry
key can compare against even a plain request after a hash collision. Unknown
registry or visibility keys, opaque dependency forms, and explicit pipelines
or slot declarations keep ordinary compilation. The existing cycle footprint,
retention-context keys and unsafe-descendant checks still govern reuse.

### Measurement method

The fresh baseline is `b27f196bc1b03b7b011acae7f1fc23c1164f22ff` plus the
pre-existing compatibility edits. The package snapshots differ only in
`clean_ioc/container.py`. Tests used CPython 3.14.4, BenchBro 1.0.0, macOS
26.7.3 ARM64 and an Apple M2 Max. Dependencies were funcie 0.2.0, typetoolbox
0.4.0 and typing-extensions 4.16.0, with lockfile SHA-256
`dbdf4ff668bcc32ab220899f2d28add11b62de86ea0dfe6adeb3bdad17a6fb79`.

The BenchBro harness in `.benchbro/v2-perf-04/probe.py` times fresh declarations
and compilation of the [four-route fixture](../../benchmarks/graph_memory_fixture.py)
with automatic GC and without tracing. The verify control includes
`create_runtime()`. Each of seven repeats and two warmups builds one fixture,
then runs full activation and identity validation and closes it outside timing.
The [compiler build controls](../../benchmarks/bench_compiler_optimization.py)
time eight declaration, compile and close operations per repeat with automatic
GC disabled. A diamond with `DerivedServices(object)` and consistently rejected
applicability checks covers a composition where all 63 generated target checks
reach the callback.

Fresh-process tracing starts after imports and GC, includes declarations and
compilation, and samples peak and retained Python allocations separately. The
latter is sampled after another GC while the runtime and optional report are
alive. Activation and cleanup run after tracing. The existing
[memory runner](../../benchmarks/runtime_memory_evidence.py) exposes the same
four-route allocation boundaries. The local harness additionally counts graph
records by type and validates the activated fixture on every sample.

### Measured benefit and tradeoff

Three alternating pairs with the selector-purity guard measured median build
time of **545.0 → 363.3 ms** (−33.3%). Run medians ranged from 541.3–553.5 ms
before and 355.5–375.4 ms after. Verify measured 1,356.4 → 1,352.7 ms. Complete
build controls without generated decorators moved from −1.2% to +2.8% across
six workloads, with overlapping run ranges. The broadest timing CV was 12.6%
in one explicit collection run.

One follow-up pair with the stricter registry and dependency guards measured
**526.5 → 354.7 ms** (−32.6%) for build and 1,338.7 → 1,341.9 ms for verify.
In that pair the plain build controls moved by −0.3% to +7.2%. The larger
single-pair increases are inconclusive. The matched diamond control measured
12.79 → 12.74 ms, with 63 applicability calls in every build. Final candidate
timing was stopped after one pair once review established the rejection.

In the three completed selector-guard pairs, median build peak traced
allocations were **6,906,442 → 6,566,619 bytes** and retained after GC were
**1,179,469 → 1,131,432 bytes**. The stricter candidate yielded 6,566,446
peak and 1,131,322 retained bytes in its one sample, compared with 6,906,631
and 1,179,595 baseline. Build retained **3,198 → 3,220** physical records in
both comparisons. The runtime retains nine additional `RouteDependency`
and two additional `Policy` registration records with eleven value records.
A cache hit clones occurrence records for inspection while its original
executable step still references the original records. Verify retained
3,198 records on both versions and traced allocation differences stayed
under 2 KiB. All samples preserved template calls, bindings, 48 workers,
3,024 transient tree objects, singleton identities and 14 managed scopes.

### Validation and decision

Local `make ci` passed on CPython 3.11.13 (2,669 passes, 8 skips), 3.12.11
(2,674 passes, 3 skips), and 3.13.5, 3.14.8 and 3.15.2 (2,677 passes each).
These checks ran on macOS ARM64. Independent review by
`/root/v2_item04/review` passed 77 focused tests and confirmed regressions
from the initial candidate for custom MRO equality and opaque registry
hashing. The revised candidate restores those calls, including equality
from a colliding opaque registry key.

**Decline.** A public reproduction still changes runtime behavior. Two roots,
`First` and `Second`, depend on the same `Infrastructure → Leaf` subtree.
During compilation of `First`, a matched generated applicability callback
changes the function exposed by `Leaf.__wrapped__` from synchronous to
asynchronous and returns false. The baseline reads the descriptor again
while compiling `Second`, and `resolve(Second)` raises because it requires
`resolve_async()`. The candidate reuses the earlier subtree, skips the
descriptor read and resolves `Second` synchronously. The registration and
dependency types in this example use ordinary classes. Selector purity
and inert registry keys therefore cannot establish invariance of the
compilation they skip. A broader audit of opaque compiler inputs is outside
this item. The candidate remains available for a scoped stash.

Reproduction and raw measurements are under `.benchbro/v2-perf-04/`.
From the repository root, run the reproduction with each captured package.

```sh
for variant in baseline candidate; do
  PYTHONPATH="$PWD/.benchbro/v2-perf-04/$variant" \
    .venv/bin/python -P .benchbro/v2-perf-04/wrapped_descriptor_repro.py
done
```

## Stash record

The implementation and regression-test candidate were stashed by the coordinator.
No item 04 production changes are retained in the working tree.

- Stash at creation: `stash@{0}`
- Immutable stash commit: `b9c67d31b685930ea47e9d15a7477639527e4377`
- Message: `v2 item 04 declined: subtree reuse changes opaque wrapper behavior`
- Decision: the build-time gain does not justify changing application wrapper hooks or synchronous/asynchronous resolution behavior. A broader compiler-purity redesign is outside this work item.

Use the immutable commit to identify this stash if later stashes change its number.
This result note is retained separately from the stashed implementation.
