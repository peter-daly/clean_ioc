# 19 — Execution-plan optimization

Created: 2026-10-04\
Status: Implemented and independently reviewed; APPROVE / KEEP\
Priority: P2\
Baseline: Clean IoC 2.0.0b30 at `eacdf70` on `codex/compiler-optimization`\
Dependencies: Existing frozen steps, occurrence graph, ownership/sharing analysis, and compilation profiler\
Related work: [Instance-sharing groups](02-instance-sharing-groups.md),
[compilation profiler](11-compilation-profiler.md),
[runtime profiler](12-runtime-resolution-profiler.md), and
[incremental compilation](18-incremental-compilation.md)

## Outcome

Investigate reducing execution-plan allocation or execution overhead by sharing equivalent immutable structure or
simplifying safe step sequences within one compiled build. Preserve separate graph occurrences so selection,
provenance, ownership, and runtime attribution remain inspectable.

This item concerns the representation produced by a build. Item 18 concerns reuse across builds; neither is a
prerequisite for the other. Exact optimizations and public configuration remain undecided until measured evidence
identifies a useful, provably equivalent transformation.

The selected delivery removes discarded implementation-type normalization while cloning occurrence metadata.
It preserves the complete eager plan and introduces no public API or new executable sharing relationship.

## Current foundation

The runtime already uses lifespan-specialized steps, direct root maps, cached-root fast paths, frozen async capability,
and selected shared/anchored initializer plans. Graph occurrences intentionally preserve different parents and
dependency contexts even when they refer to the same registration. Profiler attribution already distinguishes actual
activation from the graph edge consuming a cache.

Do not replace those specialized paths with a generic dispatcher or assume repeated service types imply equivalent work.

## Required equivalence model

Before sharing or simplifying a step, account for its effective service and implementation, bound arguments, selected
dependency steps, generic specialization, decorators, pre-configurations, resolution-context bridges, async capability,
cache/cleanup owners, scope policy, and occurrence-sensitive behavior. Public graph equality alone is insufficient.

Mutable initializer/coordinator state cannot be shared solely because immutable step descriptions match. Reuse must
follow the existing registration and owner semantics, never create a new application-instance sharing relationship.

## Required constraints

1. Preserve factory/constructor/decorator invocation counts, pre-configuration semantics, dependency order where
   defined, callback behavior, and all four concrete lifespans. Sharing an executable object must not merge transient
   products or separate per-resolution products that currently share.
2. Keep singleton/scoped cache keys and owners correct. Preserve cleanup ownership, acquisition/finalization order,
   exception aggregation, cancellation, and concurrent initialization behavior.
3. Preserve occurrence-specific derived arguments, contextual filters/preferences, generic bindings, slots,
   visibility, and anchored parent singleton composition. Structural similarity is not proof of equivalence.
4. Graph paths, selected/rejected explanations, policy findings, source-linked SARIF, semantic diffs, ownership,
   activation analysis, and sharing reports remain truthful. Do not collapse diagnostic occurrences to save step memory.
5. Observed plans retain exact calling-edge and activation attribution. An optimization must not attribute one shared
   initializer's work to every graph path or make profiler counts disappear.
6. Existing ordinary runtime paths remain specialized. No per-resolution graph traversal, equivalence calculation,
   optimizer checks, or new observer branches belong on the uninstrumented hot path.
7. Changes to internal plan representation preserve default public manifests/fingerprints when composition semantics
   are unchanged. Optimization metadata belongs in compiler profiling or an optional diagnostic sidecar.
8. Add only transformations with a documented proof boundary and measured benefit. Do not ship broad automatic
   common-subexpression elimination, arbitrary factory memoization, or speculative parallel activation.

## Scope and verification

Start by measuring emitted step counts, allocation, build cost, and runtime cost for repeated generic subgraphs,
diamonds, large collections, and parent/overlay sharing. Evaluate small internal transformations first; no new public
optimizer framework is required.

Compare optimized and baseline executions for returned identities, activation traces/counts, scoped/per-resolution
sharing, custom selection/derived values, decorated resources, providers/maps, per-call boundaries, and cleanup.
Include async contention, failures, cancellation, templates, aliases, and profiling attribution. Integrate managed
providers and warm-up plans only if those features have landed by implementation time.

## Stages when resumed

1. Identify a measured source of avoidable plan cost and specify exact eligibility and equivalence conditions.
2. Implement one narrow transformation with before/after compiler and runtime evidence.
3. Verify complete graph/report equivalence plus behavioral lifecycle and observed-path correctness.
4. Run supported-Python checks and repeatable measurements, then obtain independent review before expanding scope.

## Acceptance criteria

- A documented transformation reduces a measured cost without changing application-instance identity, activation,
  selection, cleanup, or exception behavior.
- Occurrence graphs and all related diagnostics/observations stay accurate and deterministic.
- Runtime and compilation regressions are measured and justified; enabled profiling continues to describe real work.
- A transformation without convincing equivalence or useful benefit is declined or remains experimental rather than
  weakening the compiler's guarantees.

## Scheduling

Pre-change timing, allocation and compilation profiles are recorded in
[the compiler baseline](compiler-optimization-baseline.md). Eager provider-root expansion dominates the measured
wide-root build and is the first concrete representation target to investigate.

The maintainer prioritized this item on 2026-10-04 after item 18. Baseline benchmarks precede all compiler changes;
measure the completed item 18 state as well so item 19's impact can be distinguished. Sol High implements this item
and a separate Sol High agent reviews it before item 20 starts. Benchmark evidence selects the implementation target;
the common work-list CI, documentation, performance, and independent-review requirements apply.

## Selected transformation and proof boundary

`_clone_component_tree` previously called `_draft`, which normalized the implementation type, and immediately
replaced that result with `source.implementation_type`. `_draft` now accepts an explicitly captured private
implementation-type override; only the clone path supplies it. A dedicated unset sentinel distinguishes an omitted
argument from any captured value. Fresh registration, synthetic provider, collection and diagnostic occurrences
still normalize their implementations normally.

This eliminates a discarded calculation, without caching analysis or changing plan topology. The source type is
copied by reference exactly as before, including enrichment during source inspection. Every clone still gets a fresh
draft, occurrence ID, parent/dependency/decorator/pre-configuration links, and the original ownership computation.
The subsequent owner remapping, managed-acquisition ownership reason and graph-specific explanation sidecars stay
unchanged. No initializer, coordinator, cache, cleanup state, executable step or application object gains sharing.
Generic mappings and derived values are untouched. There is no runtime compiler work or new runtime branch.

Only redundant introspection is removed: cloning does not re-read factory signatures or type aliases to compute a
value it will discard. The public composition callbacks (filters, preferences, derivations, templates and rules) keep
their invocation/order semantics. Arbitrary side effects in custom introspection descriptors are not promised a
particular count of discarded reads. Exceptions from those incidental repeated reads are removed too: independent
review constructed a custom factory whose `__signature__` getter was changed to raise by `decorator.when` after the
source type had been captured. The callback ran once in both paths; the old clone failed on its discarded read,
while the optimized clone succeeded with the captured metadata. Therefore the proof covers frozen plan facts and
composition callback semantics; arbitrary mutation of introspection state during callbacks can change incidental
build failures. The compilation-process documentation recommends pure filters and derivations. Fresh-occurrence
validation, changed declarations and repaired builders still follow their ordinary reflection paths. This boundary
does not extend to cross-build signature caching or suppressing required validation failures.

The differential tests compile the same prepared declaration snapshot through the optimized path and a shim that
reproduces the discarded normalization plus overwrite. They compare every frozen graph record, including hidden
provider occurrences; occurrence, parameter, generic, decorator and origin sidecars; complete manifests and default
fingerprints; text/Mermaid, ownership, sharing, activation and census reports; build reports/diffs; and retained
executable inventory. Fresh generated registration IDs are aligned by corresponding occurrence solely inside the
test comparison. Six existing real-constructor shapes and an anchored parent overlay pass. Additional tests prove
fresh normalization still runs and cloning preserves an enriched or explicitly unknown implementation type without
normalizing it. Existing full suites verify lifecycle identity, call ordering, resources, per-call boundaries,
providers/maps, warm-up, generics/aliases/templates, async failure/cancellation/contention, policy/SARIF, and exact
observed calling-edge versus activation attribution. The public compilation-process prose documents the captured-metadata introspection boundary; no API was added.

## Verification

On the final production source, `make ci` passed (Ruff, formatting, ty, 1,642 tests, executable docs and ordinary
benchmark discovery), as did strict MkDocs with `--site-dir /tmp/item19-docs`. Isolated existing environments at
`/tmp/clean-ioc-warmup-py{311,312,313,314}` ran the full tests, executable docs and ordinary benchmark discovery
without switching the shared `.venv`: Python 3.11 had 1,634 passed / 8 skipped; 3.12 had 1,639 passed / 3 skipped;
3.13 and 3.14 had 1,642 passed. The version-gated skips and existing single warning remain unchanged.
Final logs are `/tmp/item19-ci-final.log`, `/tmp/item19-docs-final.log`,
`/tmp/item19-focused-final.log`, and `/tmp/item19-py{311,312,313,314}-{tests,docs,discovery}-final.log`;
the rendered site remains `/tmp/item19-docs`. Earlier verification logs are preserved.

Independent Sol High verification also passed 379 existing targeted tests, the ten new proof tests, and a separate
foreign frozen-graph clone probe preserving enriched metadata and source-specific origins. The final independent
Sol High decision is **APPROVE / KEEP**, with no unresolved findings. Review accepts the explicitly documented
custom-introspection boundary and limited performance claim. The parent records the reviewed change locally.

## Measurements and decision

All captures used CPython 3.14.4 on the same macOS arm64 host. Production and fixtures were frozen for the final
captures. Named baselines and explicit `--no-compare` preserve the original baseline/history/results. Latency used
25 fixed repeats and five warmups, with unchanged case sizing: eight invocations per build repeat, and 1,000 batches
of 100 operations per runtime repeat. Declaration + build includes declarations and close; build-only fixtures
exclude fresh declarations and normal close. Runtime containers are prebuilt and warmed. Instrumented allocation
and cProfile probes are separate from latency. Commands are in [the benchmark guide](../benchmarks/README.md#captured-clone-metadata-item-19).

The isolated pre-item-19 latency is `/tmp/item19-before-2.{json,md,log}`. The preliminary `/tmp/item19-before-1.*`
overlapped the evidence helper and is excluded. The pre-change evidence helper's durations are diagnostic attribution
only because it also overlapped that preliminary run. Its exact process-local work counts and allocation samples
remain valid. The original committed baseline at `eacdf70` used the same production code and fixture definitions;
its standalone profiles and all original files remain untouched.

Across five build-only builds, every removed normalization corresponds exactly to one unchanged cloned occurrence:

| Shape | Normalization calls before → after | Unchanged clone calls | Signature calls before → after | Drafts per build / retained unique steps |
| --- | ---: | ---: | ---: | ---: |
| wide-24 | 5,400 → 3,480 | 1,920 | 120 → 120 | 1,080 / 696 |
| diamond-depth-5 | 6,095 → 1,055 | 5,040 | 315 → 315 | 1,219 / 211 |
| generic-8-roots | 7,840 → 2,080 | 5,760 | 1,700 → 420 | 1,568 / 416 |
| collection-12 | 3,250 → 1,170 | 2,080 | 785 → 785 | 650 / 118 |
| template-12 | 3,250 → 1,170 | 2,080 | 1,145 → 1,145 | 650 / 118 |
| managed-warmup | 705 → 305 | 400 | 275 → 35 | 141 / 61 |

Normalization attempts fall 35.6–82.7% across these shapes. Generic roots remove 1,152 normalizations and 256 signature
reads per build; managed/warmup removes 80 normalizations and 48 signature reads per build. This is meaningful,
deterministic compiler work elimination at a metadata-copy boundary. Required signature validation, declaration
parsing, specialization, selection and all supported compiler counters are unchanged. All six complete executable
inventories (including class counts, shallow bytes, tuple counts and graph dimensions) are identical. These changes
preserve every eager provider/collection plan; they do not reduce step count or public/hidden graph occurrences.

Unprofiled median latency, milliseconds (the two after columns are unchanged source):

| Shape | Declaration/build before | After 1 / after 2 | Build-only before | After 1 / after 2 |
| --- | ---: | ---: | ---: | ---: |
| wide-24 | 50.248 | 43.278 / 41.990 | 47.029 | 43.180 / 45.465 |
| diamond-depth-5 | 50.979 | 46.810 / 46.526 | 51.142 | 58.726 / 49.478 |
| generic-8-roots | 93.675 | 64.299 / 71.853 | 86.434 | 74.378 / 70.056 |
| collection-12 | 32.794 | 28.237 / 33.310 | 29.394 | 34.557 / 29.953 |
| template-12 | 34.412 | 34.375 / 33.223 | 35.694 | 38.392 / 39.886 |
| managed-warmup | 7.354 | 5.754 / 5.356 | 6.092 | 5.583 / 6.095 |

Generic build-only is 13.9% and 18.9% faster in the two captures, and declaration/build is 31.4% and 23.3% faster.
These are observed sample differences, with CV 9.6% before and 15.9%/10.9% after for generic build-only. Other cases
move in mixed directions: template build-only is 7.6%/11.7% slower, for example. Unchanged after-code drift reaches
18.0%; the broader original baseline already showed substantial drift. No general build speedup, exact causal
percentage, or confident broad regression/improvement claim follows from this environment. The deterministic work
reduction and repeated generic results support keeping this narrow change; the retained-plan and runtime proof
limit the scope of the performance claim.

Five-sample traced peak / retained allocation medians, bytes:

| Shape | Peak before → after | Retained before → after |
| --- | ---: | ---: |
| wide-24 | 1,714,872 → 1,714,419 | 1,493,953 → 1,493,452 |
| diamond-depth-5 | 1,896,295 → 1,896,358 | 1,636,564 → 1,636,651 |
| generic-8-roots | 2,793,971 → 2,794,743 | 2,385,691 → 2,386,408 |
| collection-12 | 859,776 → 859,745 | 723,674 → 723,643 |
| template-12 | 1,045,033 → 1,044,907 | 752,303 → 752,177 |
| managed-warmup | 245,836 → 244,462 | 186,079 → 185,985 |

Retained allocation is effectively unchanged. These small movements reflect interpreter/cache/allocation variation;
there is no demonstrated plan-memory saving. Tracing excludes declarations, measures Python allocation rather than
RSS, and includes runtime/plan metadata. Post-release counts remain captured in the raw evidence and do not prove a leak.

Uninstrumented runtime controls (microseconds per batch of 100, all unchanged runtime code and executable structure):

| Path | Before | After 1 / unchanged after 2 | CV before / after 1 / after 2 |
| --- | ---: | ---: | ---: |
| ordinary resolve | 39.292 | 40.446 / 46.455 | 16.6% / 14.3% / 17.3% |
| ordinary provider | 64.601 | 63.682 / 58.746 | 19.0% / 20.2% / 19.9% |
| child scope | 172.754 | 171.435 / 178.203 | 12.5% / 9.4% / 12.6% |
| per-call | 1,326.349 | 1,622.260 / 1,404.717 | 5.8% / 15.0% / 9.1% |

The first per-call capture increased 22.3%, so a justified unchanged-code repeat was run after the standalone evidence
helper finished. The repeat increased 5.9% over before and fell 13.4% versus after 1. Ordinary resolve moved 14.9%
between unchanged after runs too. Both results remain recorded; runtime regressions are not ruled out by these
measurements. Attribution to this build-only change is unsupported: production runtime code, frozen steps and
metadata/observed semantics are unchanged, and between-run drift is material. There is no runtime speedup claim.

### Sources, artifacts and digests

- Latency: `/tmp/item19-before-2.*`, `/tmp/item19-after-{1,2}.*`, `/tmp/item19-runtime-before.*`,
  `/tmp/item19-runtime-after.*`, and `/tmp/item19-runtime-after-2.*` (`json`, `md`, `log`).
- Counts/allocation: `/tmp/item19-{before,after}-evidence.json`, full six-shape compilation-profile JSON,
  failure profile JSON, and twelve raw `{shape}-{build,declarations}.prof` files for each prefix.
- Exact extracted work counts: `/tmp/item19-{before,after}-normalization-work.json`; combined evidence:
  `/tmp/item19-comparison.json`. Raw function counts can be inspected with
  `uv run python -c 'import pstats; pstats.Stats("/tmp/item19-after-generic-8-roots-build.prof").print_stats("normalize_implementation_type|_clone_component_tree|signature")'`.
- Before production `clean_ioc/container.py`: `c23e5a53a40b2387e6171d648db46b47a2315bc034fc86ea0716f93c9a355b5b`.
- Final production: `2ef8c334768936a9d7f8b9773c51d467d128c9e55c815cb9251636f2ba8746ab`.
- Unchanged latency fixture: `70a2a037e26df5fa4daf02e66af484687ebee5604e8a92c58a18d6e1dc6b733d`.
- Unchanged evidence helper: `97b7744ffc349560cc207e811a4deae382527f40ee7c0147af0ab697f3d66c4a`.
- Unchanged lockfile: `0a39ba6f6ac45ec27723907c0ab79a48797517dee1274187ea6e49574ab09be5`.
- Focused tests: `d1796ff328e66985ab2b4324676e1e92a4f02b8613822a7772e89cec28fca280`.

No profiles were truncated and all compiler evidence builds had zero application activations. Aggregate work/profile
artifacts contain no application values, owner IDs or callback representations. The exact behavioral boundary above,
measured CPU-work elimination, unchanged allocations/plan topology, and noisy runtime controls are part of the review.

Raw JSON capture SHA-256 identities (files remain outside Git):

| Artifact under `/tmp/` | SHA-256 |
| --- | --- |
| `item19-before-2.json` | `445d36762fd9c016958b537fba520d21ad759a5e820a23a8f6df3830491fb93b` |
| `item19-after-1.json` | `5f1082f74e8fbe0e63ee0d0fc714ea33c70bc6015cdc6cb6521aebdc61475f6f` |
| `item19-after-2.json` | `2be2c1475d0a24622a4aec8e29fa946788db1e0cfa2729787be3e0ab8f217198` |
| `item19-before-evidence.json` | `e6edc86f62d35101bebe52a288db555d4d7809b30a45a659ab9bad57b8de1e81` |
| `item19-after-evidence.json` | `8eb683179500621822b1e07dff94248ea57674d7fc90ba7789b222ec6071581e` |
| `item19-runtime-before.json` | `266dc52620fc306125084937ca395af89b1a06e8390ac2ac321fb719ed52d6b4` |
| `item19-runtime-after.json` | `2797686ee0a534ef3fb13060fa0cfcd1942f5b9b0623eb5c70885c0ae6f005cf` |
| `item19-runtime-after-2.json` | `b05b6b125f5e2344bff20030d114cf89e2c35bcfde11bdb95b0015e2bc1d112e` |
| `item19-before-normalization-work.json` | `39ffaf6583e03981d69350a7d0fb23d47b5cd3ea7d2439cd72952fe02467d9da` |
| `item19-after-normalization-work.json` | `61ebfa87ff5cfdb08658485ea97800fc5c26e3fa5a6f73a62a9bd48f3a95464d` |
| `item19-comparison.json` | `bfb74f00da674d9afbc77d4ccfa21343528d6b4283946472333f820dfec0372d` |
