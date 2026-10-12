# Task 05 result — retain the optional reduced runtime

Implemented by GPT-6.1 Sol with high reasoning on 2026-10-09, starting from the
`2679234` task-04 rollback on `version2`. No commit or publication was requested.
Tasks 01 and 02 remain; task 04's implementation is not restored.

## Decision

**KEEP.** Both builders now accept `explain_metadata: bool = True`. Passing `False`
releases successful-build inspection metadata, trims build-only executable
carriers, and retains only graph records required by resolution and explicitly
enabled composition. Default/full behavior remains compatible. The synthetic
fixture demonstrates a large Python-retention reduction and a smaller, separately
measured RSS improvement. It does not establish a production memory or speed claim.

The [source-backed inventory](05-inventory.md) identifies retained fields and their
readers, ownership and optional-capability conditions. The public contract and
executable example are in [compiler tooling](../../docs/compiler-tooling.md#optional-explanation-metadata).

## Implementation and capability boundary

- Runtime root selection, `has_component`, collections, providers and maps,
  context/dependency relationships, lifetimes, cache and cleanup ownership,
  provisions, warmups, build settings and instrumentation remain supported.
  The closure includes ancestors, siblings, decorators, owners, pre-configurations,
  all executable targets and negative provider projections. Original Component
  identities and steps are preserved. Ordinary resolution gains no graph walk.
- All fields on retained Components remain available to runtime filters, including
  names, tags, generic bindings, aliases, declared types and build inputs. Primary
  records outside that closure are actually removed. Successful explanation,
  provenance, candidates and census indexes are emptied; inspection graphs and
  caches, validation rules and the selected-registration catalogue are released.
- Fresh reduced registration steps retain only ID, service type, implementation,
  activator and lifespan. Decorator/pre-configuration carriers shed build callbacks,
  dependency settings and declaration context while keeping compiled execution,
  state and ownership. Inherited carriers and ancestor graphs are never mutated.
- Required final validation and warmup planning happen before pruning. Reduced
  primary compilation freezes only the successful runtime/architecture closure;
  optional instrumentation captures private paths before final architecture-only
  pruning. Failed final validation freezes the complete failure graph. Diagnostics
  are independent: either diagnostics setting releases successful explanation
  data, while failed builds preserve the requested existing evidence.
- `graph`, graph-dependent analysis/explanation/manifest/census/architecture APIs,
  `selected_registrations` and `validation_report()` fail with
  `explain-metadata-disabled`. Build reports retain scalar findings/root counts.
  Validation-only rules reject reduced builds before compilation. Build-mode rules
  still run. Deferred unreachable checks remain deferred with
  `check_unreachable=False`; reduced runtimes cannot request them later.
- Ordinary scopes inherit their plan mode. A full parent permits full or reduced
  overlays; a reduced parent requires `ScopeBuilder.build(explain_metadata=False)`.
  Future overlays retain only necessary declaration layers/boundaries and private
  architecture anchors. Completed template/source-inspection evidence is dropped.
  Scope builders are not silently disabled.
- Callback Components are valid during compilation. After a successful reduced
  build, discarded primary views expire clearly while occurrence IDs stay available;
  retained views keep all their runtime relationships. Detaching full connected
  snapshots would preserve the discarded owner closure and defeat pruning, so no
  escape tracking, copies or tombstones are added. Saved validation CompiledGraphs
  expire and release context/caches. Separate source snapshots and caller-created
  reports remain usable and caller-owned; saved bound methods do not reconstruct
  released metadata. Class-level `CompiledGraph.type_ast(type)` is independent.
- Build matrices retain their existing full-graph contract. The private schema-5
  artifact experiment rejects reduced plans before writing; full round trips still
  work. Profiling remains usable, while analyses requiring a full graph need an
  independently retained one.

## Repeated measurement method

The fresh [rollback baseline](evidence/05-before.json) precedes runtime edits.
Final groups use identical production, fixture and runner hashes, with three
serial fresh normal processes and three separate traced processes per group.
No tests or benchmarks ran concurrently. Interpreter: Python 3.14.4; macOS ARM64;
eight routes; instrumentation disabled. The 32-route fixture was not attempted.

Build time includes fixture import, composition and compilation. Timings and RSS
come from normal processes; collected retained allocations and allocation peaks
come from separately traced processes. `prepared` is after build and collection;
`resolved` is after the complete resolution workload and collection, before
inspection/census. RSS includes the interpreter, imported code and native allocator
retention. Heap measurements do not predict RSS. Raw samples record source/local
changes, options, ownership, resolution checks and memory at both boundaries.

Unless named otherwise, diagnostics and future scope builders are disabled, the
builder is released and no callback views escape. Composition and caller-owned
experiments change only their stated ownership/capability options. Disabled API
attempts run after measurement, twice, and assert that no metadata/cache is rebuilt.

| Group | Build s | Resolve ms | Retained Python MiB | Build allocation peak MiB | Current / peak RSS MiB | After-resolution Python MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| [Fresh rollback baseline](evidence/05-before.json) | 11.283 | 23.188 | 38.430 | 73.578 | 132.797 / 132.797 | 39.552 |
| [Final full metadata](evidence/05-final-full.json) | 11.011 | 22.436 | 38.431 | 73.569 | 134.156 / 134.156 | 39.554 |
| [Final reduced metadata](evidence/05-final-reduced.json) | 10.871 | 14.286 | 3.097 | 72.844 | 129.453 / 129.453 | 4.220 |
| [Reduced + future overlays](evidence/05-final-composition.json) | 10.933 | 14.367 | 3.279 | 72.844 | 129.469 / 129.469 | 4.401 |
| [Reduced + caller-owned builder/views](evidence/05-final-caller-owned.json) | 10.977 | 15.135 | 5.517 | 75.145 | 131.141 / 131.141 | 6.640 |
| [Diagnostics + full metadata](evidence/05-diagnostics-full.json) | 8.478 | 112.621 | 250.972 | 286.851 | 355.359 / 355.359 | 252.095 |
| [Diagnostics + reduced metadata](evidence/05-diagnostics-reduced.json) | 8.384 | 15.003 | 3.097 | 290.055 | 350.844 / 351.844 | 4.220 |

Normal-process prepared RSS sample ranges:
- Fresh rollback baseline: 130.875–133.562 MiB.
- Final full metadata: 132.578–134.438 MiB.
- Final reduced metadata: 129.422–129.453 MiB.
- Reduced + future overlays: 128.156–129.750 MiB.
- Reduced + caller-owned builder/views: 130.750–131.984 MiB.
- Diagnostics + full metadata: 355.031–355.422 MiB.
- Diagnostics + reduced metadata: 350.828–354.266 MiB.

The [comparison ledger](evidence/05-comparison.json) records medians, ranges,
source agreement, independent behavior agreement and graph/plan censuses.
Current and peak RSS medians after resolution equal the prepared medians for all
seven groups; allocation peaks also remain dominated by compilation.

The final diagnostics-off comparison saves **35.33 MiB (91.9%)** of collected
Python allocations and **4.70 MiB (3.5%)** of measured RSS. Relative to the fresh
rollback baseline, reduced RSS falls **3.34 MiB (2.5%)**. Build time changes
11.011→10.871 s and resolution 22.436→14.286 ms in this synthetic workload;
three samples establish these observations, not a general speed guarantee.

With diagnostics enabled, successful Python retention still falls
**250.97→3.10 MiB**, but RSS only falls **355.36→350.84 MiB**. Reduced diagnostic
build allocation peak is **3.20 MiB higher** (286.85→290.06 MiB, about 1.1%).
Diagnostics still capture complete temporary facts for truthful failure evidence;
their compilation allocation and native retention are not eliminated by the flag.

All reduced container-only groups retain **8,982 physical records**, comprising
8,932 public relationship records plus 50 runtime/provider records. Full mode
retains 88,558; reduction removes 79,576. Both retain 1,765 execution steps and
116 shared definitions. Successful explanation/census/candidate entries and
build-only registration/decorator dependency settings are zero in reduced mode.

Enabled future scope builders add **0.181 MiB** of collected Python retention
(3.097→3.279 MiB), keeping declaration composition but no source graphs in this
fixture. RSS changes 129.453→129.469 MiB, smaller than process variation. Keeping
the caller builder and 320 callback views adds **2.419 MiB** (3.097→5.517 MiB)
and raises median RSS to 131.141 MiB. The caller owns eight separate snapshots
containing 7,104 additional records; 256 saved views refer to the primary graph
and 64 to those snapshots. These data are not attributed to the container alone.

Full-mode inspection is measured separately after runtime snapshots. In the three
normal processes, median first/repeated times are: 128 explanation samples
99.98/28.71 ms, traversal 93.21/93.55 ms, and manifest 551.34/0.017 ms.
Fresh inspection tracing observes about 13.55 MiB additional retained Python
data and 25.63 MiB peak; repeated inspection adds about 1.5 KiB after the first
pass. These costs are excluded from runtime memory medians. Reduced inspection
attempts fail clearly without changing the captured census or constructing caches.

All final groups produce identical independently checked resolution signatures,
activation counts, lazy targets and template callback counts. These cover 7,812
tree objects, 3,968 leaves, 124 workers, 26 managed scopes, one ordinary scope,
64 source-map calls and 507,904 bytes of retained payload. Full inspection retains
fingerprint `fa06427a9c823d18961ba2d173294ce206f38c516f2478dd229e7d1bebaaa722`
on both first and repeated inspection in all six full-mode processes. Reduced
mode deliberately has no complete manifest or logical inspection census.

The full/default retained Python total differs from the fresh rollback baseline
by only about 1 KiB. Its measured RSS is higher, including a larger initial runner
import footprint (about 40.73→41.67 MiB) and process variation. The final same-source
comparison isolates the option; the separate rollback comparison is also reported.
The collected runtime floor is about 3.1 MiB here, but compilation's temporary
facts and allocator retention leave process RSS and allocation peak much larger.
Diagnostics increase that compilation floor even when successful metadata is dropped.

## Rejected probes and retained limitations

An initial attempt to skip temporary compact decorator explanation capture lowered
build time substantially but increased normal-process RSS to about 167 MiB; pruning
without that capture still measured about 160 MiB. Keeping the existing temporary
capture and releasing it after success measured about 129 MiB. That attempt was
rejected. The final implementation does not force extra compilation collections or
hide high RSS with traced measurements. All prototype files are preserved as
exploratory evidence, not mixed into final comparisons.

A full ancestor, caller-owned builder/callback, declared runtime callable/value,
source snapshot or profiling report can retain its own data. Reduced descendants
cannot release those owners. Private architecture adds records where a composition
actually has private-only roots; the rich fixture's enabled-composition comparison
has no extra private-only records, so the separate boundary/instrumentation tests
verify that path. Arbitrary application values are opaque to the new closure walk,
including objects with `__class__` traps and literal private-step-shaped values.

## Verification

The [check log](evidence/05-checks.json) records exact commands and outputs:

- Full Python 3.14.4 suite: **2,127 passed**, including 48 focused reduced-mode
  cases. The existing FastAPI/Starlette deprecation warning remains.
- Forced reduced builds reuse **222 existing execution tests**, with 16 tests
  requiring complete inspection deliberately deselected. These cover ordinary and
  managed typed providers, provider maps, isolated per-call scopes and aliases.
- Ruff lint/format, type checking, executable documentation examples, BenchBro
  discovery and final whitespace checks pass.
- Strict MkDocs reports the same **eight existing links outside the docs tree**
  and aborts; no new link warning was introduced. This existing limitation is
  preserved, not counted as a successful strict documentation build.
- Independent reduced [runtime](evidence/05-audit-reduced.json) and
  [composition](evidence/05-audit-composition.json) audits account for every retained
  record and report no missing graph-qualified runtime links. The two-route
  [escaped-view audit](evidence/05-audit-escaped.json) deliberately observes eight
  expired inspection-only IDs, two caller-owned snapshots and no broken runtime
  links. A regression test makes a runtime owner link invalid and proves the audit
  distinguishes it from permitted expired callback views.

Focused cases cover all diagnostics/metadata combinations, full/reduced parent-child
combinations across all four lifespans, no ancestor mutation, generic bindings,
relationships used by filters, failed builds and final validation, validation-only
rejection/reuse, saved callback and bound-method behavior, warmups/provisions,
private boundaries/instrumentation, carrier callback collectability and schema-5
rejection. Existing full artifact round trips remain covered by the suite.
Other supported interpreters and remote CI were not run for this local task.

## Reproduction and evidence

Each final file was captured with `python -m benchmarks.graph_memory_evidence repeat
--routes 8 --repeats 3 --output <new-file>`, adding the recorded mode/ownership flags.
Full/reduced base groups use `--inspection`; reduced adds `--no-explain-metadata`.
Composition adds `--allow-scope-builders`; caller-owned adds `--retain-builder
--capture-selection-views`; diagnostics adds `--diagnostics`. Every group serializes
normal and traced child processes. The raw files preserve current/peak RSS and
collected Python retention both immediately after build and after resolution.

Earlier `05-prototype-*`, `05-draft-pruning-8`, `05-capture-probe-8`,
`05-discard-facts-probe-8`, `05-full` and `05-reduced*` files retain exploration and
intermediate source evidence. They are not final same-source samples. The final
runtime, fixture and runner hashes remain those in the comparison ledger; only
work-plan/result documentation was completed afterward.
