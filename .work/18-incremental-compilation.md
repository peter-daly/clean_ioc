# 18 — Incremental compilation

Created: 2026-10-04\
Status: Investigation complete and independently reviewed; production cross-build cache declined for this delivery\
Priority: P2\
Baseline: Clean IoC 2.0.0b30 at `eacdf70` on `codex/compiler-optimization`\
Dependencies: Existing composition snapshots, occurrence-specific compilation, and compilation profiler\
Related work: [Compilation profiler](11-compilation-profiler.md),
[build matrices](../.v2_roadmap/04-build-variant-matrix-checking.md), and
[execution-plan optimization](19-execution-plan-optimization.md)

## Outcome

Reduce repeated compiler work across related fresh builds, overlays, or matrix variants by reusing analysis that is
provably unaffected by the changed composition. Every build still produces its own immutable runtime with correct
selection, values, owners, graph occurrences, diagnostics, and validation results.

This is a prioritized investigation and implementation item. Reusing an entire executable plan is not assumed safe, and
no public cache API or performance claim is accepted by this document.

## Current foundation

The compiler already caches selected specialization work within a build and reuses anchored parent singleton and
pre-configuration steps in overlays. Item 11 measures actual compilation phases, callback costs, and repeated work.
`BuildMatrix` deliberately requests fresh builders and closes each built runtime after capturing its report.

This item investigates reuse beyond those existing mechanisms; it must preserve matrix freshness and lifecycle rules.

## Design questions to settle before implementation

- Which work dominates representative repeated builds: signature/type processing, generic specialization, structural
  candidate expansion, callbacks, ownership analysis, diagnostics, or validation? Establish this with actual profiles.
- Which results are immutable analysis, and which embed configured values, parent context, registration identity,
  owner tokens, callback state, or runtime initializer/cache state?
- Can a trustworthy composition revision and dependency index establish eligibility without hashing arbitrary
  application values or treating callable identity as a purity guarantee?
- Should the first delivery reuse only signature/type analysis, or can a bounded reusable compilation snapshot
  safely support a larger subset? Public names and cache lifetime remain undecided until the evidence supports them.

## Required constraints

1. Default manifest fingerprints are not cache keys. They deliberately omit private build inputs, values, and
   contextual information that can change compilation. Equal fingerprints do not prove equivalent compiler inputs.
2. Changes to declarations, argument policies, filters/preferences, templates, visibility, generic bindings, root
   policies, slots, or build inputs invalidate affected work. In-place annotation/signature mutations and module reloads
   must also invalidate or make the source ineligible; a repaired builder cannot receive a stale cached result.
3. Preserve composition callback invocation/order and validation semantics. Do not skip filters, derivations, template
   callbacks, discovery, or rules on the assumption that they are pure. Any callback-reuse opt-in would need a separate
   explicit contract before acceptance; the initial investigation may conclude such work is ineligible.
4. Recreate occurrence-specific parent/dependency metadata and bind executable work to the new build's identities,
   values, and owners. Separate containers must never share singleton/scoped instances, coordinators, initializer
   completion, finalizers, or mutable compiler state through the reuse cache.
5. Existing anchored overlay reuse remains owner-aware. Do not change parent singleton wiring or import a parent's
   private inputs into a new composition merely because a subtree looks structurally equal.
6. Bound cache retention and define eviction, failure cleanup, concurrency, and invalidation. Do not retain completed
   runtimes or acquired resources. Private in-process analysis references are not exported as values or fingerprints.
7. Successful and failed builds retain current diagnostics, source/path explanations, builder repairability, and
   redaction. Runtime resolution stays plan-driven and gains no compiler-cache checks.
8. Reuse statistics describe actual eligible work/hits/misses and why reuse was rejected. They are compiler evidence,
   separate from runtime cache hits and graph fingerprints.

## Scope and verification

Use fresh related builds, changed build inputs, generic-heavy graphs, templates, contextual selection, and overlays as
representative cases. Compare complete compilation with reuse-enabled compilation for selected implementations,
arguments, paths, findings, ownership, activation counts, cache identity, and cleanup behavior.

Include mutable callback closure state, same callable identity with changed annotations, repaired failed builds,
changed visibility, anchored singletons, and concurrent separate builds. Verify bounds and recursively inspect
diagnostic output for private values. Reuse must never activate application objects during build.

Persistent on-disk caches, pickled runtime plans, runtime registration changes, automatic cross-process reuse, and
source-code generation are outside the initial scope.

## Stages when resumed

1. Profile representative repeated builds and record a dependency/eligibility model with explicit exclusions.
2. Select a small useful reuse boundary and a bounded opt-in design; document invalidation before implementation.
3. Implement it with full-compile equivalence tests, current tooling integration, and cache lifecycle verification.
4. Record supported-Python correctness and repeatable build-time/memory measurements; obtain independent review.

## Acceptance criteria

- Eligible reuse produces the same composition, diagnostics, callback behavior, ownership, and runtime behavior as
  full compilation, with fresh runtime caches and resource owners.
- Private values, mutable context, repaired declarations, and reloads cannot produce false cache hits.
- Reuse is bounded, inspectable, and absent from normal resolution paths.
- Representative measurements demonstrate a useful gain with stated limits; inconclusive measurements are labelled
  inconclusive. If eligibility leaves no worthwhile gain, record that finding instead of shipping an unsafe cache.

## Scheduling

Pre-change timing, allocation and compilation profiles are recorded in
[the compiler baseline](compiler-optimization-baseline.md). Signature work is a minority cost in the measured builds;
the implementation investigation must demonstrate useful eligible reuse before introducing a cache.

The maintainer prioritized this item on 2026-10-04. Capture baseline benchmarks before assigning Sol High
implementation, then obtain separate Sol High review before proceeding to item 19. The first decision is whether
measured repeated work justifies implementation. The common work-list CI, documentation, performance, and
independent-review requirements apply.

## Eligibility investigation (2026-10-04, before implementation)

The baseline identifies repeated `_validate_dependency_names()` signature inspection as a possible small boundary.
Registration dependency parsing largely happens before `build()`, and most compiler work remains occurrence-specific
provider expansion. Reusing parsed dependencies, registrations, generic mappings, or executable plans would also retain
values, callback state, mutable type evidence, or owners. Those are excluded from this experiment. All callbacks,
preparation, specialization, ownership, freezing, diagnostics, and validation rules continue normally.

| Boundary | Eligibility / invalidation evidence |
| --- | --- |
| Parameter-name validation | Candidate only for freshly checked ordinary callables; immutable names/counts/kinds control this result. |
| Dependency and type-hint parsing | Excluded: defaults, in-place annotations, deferred evaluators and global forward references can change; registration parsing also falls outside build-only timing. |
| Generic mappings/specialized registrations | Excluded: mutable type/MRO/alias evidence, registration arguments, requested bindings and generated wrappers must be reprocessed. Existing within-build reuse remains. |
| Templates, discovery, filters, preferences, derivations and rules | Excluded: callbacks execute in full, with current closure state, contextual parents, inputs, visibility and root/slot policies. |
| Occurrences, ownership and executable plans | Excluded: fresh graph parents, values, initializer/coordinator/cache/finalizer state and owners; existing explicit parent anchoring remains unchanged. |
| Composition revisions / public manifests | Insufficient: shallow snapshots still reference mutable application definitions, while public fingerprints deliberately omit private inputs. Neither proves analysis equivalence. |

The candidate reuses only an immutable set of accepted parameter names and the presence of `**kwargs`. It runs in
an isolated benchmark opt-in context; it is not a proposed public API. Each lookup rejects aliases and arbitrary
callables before normalization, custom metaclasses/constructors/descriptors, wrappers, custom signature controls,
deferred annotation evaluators, and nonstandard namespaces/annotation/default/dependency dictionaries. It freshly
observes immutable parameter names, argument counts/kinds, default count, keyword-default names, and whether class
signature inspection removes the first parameter. Annotation values and defaults never enter the cache or an
exported key. In-place code/signature/wrapper/default changes are checked again; reloads with equivalent name/kind
metadata may safely reuse that metadata, while changed shapes miss. Annotations with evaluation callbacks are ineligible,
even if a prior registration has populated `__annotations__`. In particular, CPython 3.14's deferred annotations
substantially restrict eligibility in normal annotated application code.

The experimental cache is an explicitly owned bounded LRU retaining only exact strings, integers, booleans, tuples,
and frozensets describing parameter shapes. An initial code-object-key design was rejected during retention audit:
`CodeType.replace(co_consts=...)` can embed application objects and arbitrary hash/equality behavior. The final probe
retains no code object, function, class, globals, closures, defaults, registration, builder, runtime, exception, or resource.
Eviction and clear discard analysis; failed signature inspection is not cached. It is protected by a lock for concurrent
lookups, and actual builders remain independent. Concurrent mutation of one source while compiling is not established
as a supported cache contract. Production adoption would require a separate concurrency proof and full integration
verification; the experiment cannot establish that proof by timing alone.

The complete audit and 14 focused probe tests preceded the final captures. Two preliminary captures imported earlier
guards/keys and are retained separately, excluded from conclusions. Exact builtin namespace/dependency keys are
required so checking eligibility does not invoke arbitrary equality/hash behavior. Rejected inputs fall back once to
the original validator; the guard does not evaluate constructor descriptors or aliases to discover their eligibility.

Measure baseline, conservative candidate, and an intentionally unsafe no-validation ceiling on unchanged workloads.
The ceiling is cost evidence only, never eligible behavior. Preserve the original baseline harness and callbacks.
If even the guarded candidate has no convincing useful gain, decline production reuse under the acceptance criterion
above rather than adding a public opt-in API and compiler plumbing with unsupported value.

## Investigation outcome and evidence (2026-10-04)

**Investigation complete and independently reviewed; production cross-build cache declined for this delivery.**
No compiler/runtime implementation, public API, fingerprint, profiler format, resolution path, or owner lifecycle changed.
The eligible experiment can remove repeated signature inspection locally, but the representative cross-build saving is
only one additional inspection per generic/collection build after within-build reuse. Timing does not establish a useful
incremental gain, and a larger reusable boundary remains ineligible under the required mutation/callback/owner contract.
This is a decision about the measured first delivery, not a claim that every possible future cache is unhelpful.

### Comparable unprofiled captures

BenchBro 1.0.0, CPython 3.14.4, macOS 26.7.1 / arm64 / AC power; matching baseline environment and lock.
Original fixture digest remains `70a2a037e26df5fa4daf02e66af484687ebee5604e8a92c58a18d6e1dc6b733d`.
Stable probe digest: `ddd68535721dbfcb5cc9c3da9955f21812483fef43c77607fe98c267a43249fe`.
Two final captures ran from `09:46:24.689498` to `09:53:06.643884` UTC, with other heavy agent jobs paused.
Each operation has 25 fixed repeat samples, five warmups and eight invocations per sample, GC disabled during measurement.
Fresh declarations, the patch context, complete build and normal close are included; imports/definitions and initial
probe construction are excluded. The bounded probe is warm across builders. All callbacks and other compilation run
normally except the explicitly unsafe ceiling, which omits name validation and is cost evidence only.

Each cell is run 1 / unchanged run 2; milliseconds per fresh declaration/build/close:

| Shape | Full ms 1 / 2 | Candidate ms 1 / 2 | Unsafe ceiling ms 1 / 2 | Full repeat ms 1 / 2 |
| --- | ---: | ---: | ---: | ---: |
| wide-24 | 47.58 / 43.98 | 48.75 / 42.95 | 45.37 / 43.12 | 50.32 / 42.78 |
| generic-8-roots | 79.08 / 77.17 | 89.98 / 83.37 | 90.63 / 79.25 | 85.43 / 86.72 |
| collection-12 | 32.88 / 35.04 | 26.64 / 30.74 | 23.76 / 26.14 | 31.61 / 30.23 |
| template-12 | 34.76 / 32.47 | 31.71 / 32.55 | 27.03 / 31.94 | 36.23 / 37.62 |
| managed-warmup | 6.77 / 10.17 | 6.99 / 11.73 | 6.23 / 13.07 | 6.81 / 11.06 |

39/40 rows are noisy; CV spans 6.2–34.7%, relative 95% margins 2.5–13.9%, and outliers 0–3.
Raw JSON retains every quality field and environment identifier. Collection's first candidate capture is faster than
both full controls, suggesting useful **within-build** work reduction; in run 2 it is slightly slower than the later full
control. Templates are similarly sensitive to control choice. Neither those rows nor the unsafe ceiling establish an
across-build speedup. Generic and managed/warmup rows supply no convincing aggregate benefit.

### Separate lifetime attribution

The focused lifetime capture ran `09:53:16.459424`–`09:54:57.536040` UTC with the same fixed settings and original
generic/collection definitions. Warm reuse and a probe cleared before every build both retain within-build hits;
clear is measured and slightly favors warm reuse. Exact counts over three fresh builds:

| Shape | Warm misses / hits | Cleared misses / hits | Rejections in either mode | Additional across-build saving |
| --- | ---: | ---: | --- | --- |
| generic-8-roots | 1 / 23 | 3 / 21 | 72 deferred annotations; 96 alias/nonstandard callables | 2 inspections over 3 builds |
| collection-12 | 1 / 431 | 3 / 429 | 39 deferred annotations | 2 inspections over 3 builds |

Thus cross-build warmth avoids one miss on each subsequent build. Collection already avoids 143 inspections inside
each fresh build with a cleared probe, versus one additional avoided inspection from cross-build warmth. Generic
avoids seven locally versus one additional across builds. Exact two-build counts for all six shapes, including the
diamond and zero-eligible-work managed/warmup shape, are retained in the separate evidence JSON.

| Shape / lifetime | Median ms | CV % | 95% margin % | Outliers | Noisy |
| --- | ---: | ---: | ---: | ---: | --- |
| generic / warm | 102.82 | 17.8 | 7.1 | 2 | True |
| generic / cleared per build | 90.12 | 9.4 | 3.8 | 0 | False |
| generic / warm repeat | 151.36 | 18.2 | 7.3 | 0 | True |
| collection / warm | 49.38 | 15.4 | 6.2 | 0 | True |
| collection / cleared per build | 33.96 | 12.6 | 5.0 | 2 | True |
| collection / warm repeat | 30.12 | 13.9 | 5.6 | 0 | True |

Five of six lifetime rows are noisy. The unchanged warm controls drift +47% (generic) and −39% (collection), so no
cross-build latency claim is supported. Local analysis reuse is a separate possible optimization; this item does not
ship it or preselect item 19's implementation.

### Allocation, bounds and behavioral verification

Five separate tracemalloc samples per full/candidate shape exclude fresh declarations and warm cache construction.
Median traced build peaks differ by less than 0.03% in every shape, and retained runtime/plan bytes by less than 0.04%.
There is no demonstrated plan-memory reduction; this cache changes only parameter analysis. Post-release bytes are
recorded but do not prove a leak. Warm-cache allocations are excluded from those figures; the probe retains 0–2
primitive-only entries in these shapes, with a 128-entry bound verified independently by eviction/clear tests.

Fourteen focused checks cover signature/code/default/annotation/wrapper mutation, reload-shaped definitions, custom
metaclasses/descriptors/dictionaries, code constants holding resources, weak-reference release, uncached failures,
concurrent lookups, graph/fingerprint/counter equivalence for all six shapes, zero build activations, callback closure
changes, failed-builder repair, independent singleton identities, and explicit parent overlay anchoring. They are
evidence for the isolated candidate, not a production concurrency/integration contract. Broader alias/template/provider-map,
managed-provider/warmup, async lifecycle and redaction behavior continue through the unchanged supported suites.

Supported full suites pass in separately synchronized `/tmp/clean-ioc-warmup-py311`–`py314` environments:
Python 3.11: 1,624 passed / 8 skipped; 3.12: 1,629 / 3; 3.13 and 3.14: 1,632 passed each.
Strict MkDocs and executable documentation examples pass. CI initially caught duplicate fixture registration during
automatic benchmark discovery; isolated experiments were moved outside `bench_*.py` discovery so the unsafe ceiling
also stays out of normal runs. Probe content/digest and measured function boundaries are unchanged. Explicit file/case
targets still provide the 20 analysis and six lifetime rows. Final `make ci` passes, including 1,632 tests, lint, format,
typecheck, executable docs and ordinary discovery. The final module locations also pass all 14 focused checks on each
supported Python. Independent review is recorded by completion; no production adoption is implied by probe equivalence.

### Reproducible artifacts and limits

Experimental sources: [analysis probe](../benchmarks/incremental_analysis_probe.py),
[lifetime probe](../benchmarks/incremental_lifetime_probe.py),
[separate evidence helper](../benchmarks/incremental_analysis_evidence.py), and
[focused checks](../tests/test_incremental_analysis_probe.py).
Commands and boundaries are in [the benchmark guide](../benchmarks/README.md#incremental-analysis-investigation-item-18).
No tracked benchmark results, existing machine history, or production baseline were overwritten.

- `/tmp/item18-measurement-{1,2}.{json,md}`: final comparable captures. JSON SHA-256 respectively
  `0cb877565d5907673f426e219f6e73141464c0b7b240523ad287a67fbb06040f` and
  `56dc1a94ee69590391a18c504ad431fddca9b2517750240c4147446f31b212c9`.
- `/tmp/item18-lifetime.{json,md}`: focused lifetime capture; JSON SHA-256
  `bd8770429a277f186bb84d992eed8c8959cf09c045ddb9d863ad982a6ede6e6a`.
- `/tmp/item18-evidence.json`: separate counts and allocation samples; SHA-256
  `41b9b07c17aa17cf0fa75802d7ca0d93125beef3e21fbd19c764022ded1c3539`.
- Lifetime harness capture digest: `15949d0a1acfdf19c031e8d330c8c184cc2d1a3e128c7928c6c6f5d6c5bf771a`.
  Moving its probe import to the new module location changed only that unmeasured import line; final digest:
  `d7324390295a9c6f3a7c47a54db1e167563a390c4aa2d6b77a88dd297a166792`.
- `/tmp/item18-preliminary.{json,md}` and `/tmp/item18-preliminary-2.{json,md}`: excluded earlier guard/key captures.
- `/tmp/item18-ci-final.log`, `/tmp/item18-docs.log`, `/tmp/item18-py{311,312,313,314}.log`, and discovery outputs:
  validation evidence; no new public API/example is claimed.

### Independent review

A separate Sol High agent recommends **APPROVE / KEEP the investigation; decline production cross-build caching**.
The reviewer independently passed the 14 focused tests, matched 210 original/candidate signature outcomes, checked
guard side effects and primitive-only retention, and verified ordinary/explicit benchmark discovery. The reviewer
audited raw artifact digests, count/allocation tables, timing attribution and successful CI/docs/supported-Python logs.
The discovery failure is resolved; no findings remain open.
