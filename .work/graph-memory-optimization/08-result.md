# Task 08 — compact-index investigation

Investigation complete, 2026-10-09. **REFINE; not ready for implementation.** Production sources unchanged; no commit or push.
Assigned GPT-6.1 Sol with high reasoning. Starting revision `7b9a841`.

The [inventory](08-inventory.md) defines the compiler integer-ID fast path and
mapping adapter boundary. The candidate constructs compact origins and decorator
indexes directly, preserving keys, insertion order, exact captured provenance and
referent identity. It promotes the same backing object to a dictionary for general
key access, deletion, iteration or view creation. The experimental codec encodes
unpromoted entries directly and preserves backing sharing through memoized references.

## Measurement method

The unchanged rich eight-route fixture runs with diagnostics, explanation metadata,
future scope builders and profiling disabled; callers retain no builder or inspection
views. The common loader imports precompiled, hash-verified container bytecode before
measurement. Source transformation, AST work and source compilation occur in the
separate `prepare` process. The same loader is used for the fresh same-source control;
Task 07's historical data remains read-only and is not mixed into this comparison.
Normal timings/RSS and separately traced allocations are reported independently.
Build timing includes fixture import, composition and compilation. Retained memory
follows collection. RSS is whole-process current/high-water memory, with setup RSS
recorded and never subtracted. Physical records, logical visits and execution-step
counts are separate. Census, offline accounting and compatibility checks are excluded
from build/resolution measurement intervals.

Each build variant has five fresh normal and three fresh traced processes, serially,
with candidate order reversed on alternating repetitions. Full, diagnostics and artifact
comparisons use fresh processes as recorded in their raw files. Fixture file caches
are not flushed. Python 3.14.4/macOS ARM64 is the matched performance environment.
Sources, bytecode, probe files, flags, caller ownership and run process IDs are recorded.
No Task 06 cache change or Task 07 slots/pre-lookup change is active, and independent
savings are not added together.

An initial normal-only run used generic Mapping views. A stricter check found their
missing native `.mapping` and reverse-view interfaces. Its five normal runs per
variant are preserved as `08-preliminary-build-runs.json` with the inert v1 source;
these are excluded from final claims. The corrected candidate delegates view
creation to dictionary views. The initial matrix uses archived v2; later matrices
use v3, differing only by a static-type suppression comment. Their full AST hashes
are identical (`08-probe-versions.json`), so representation and executable behavior
are unchanged. The initial driver is archived separately; `08-driver-identity.json`
records its executed-source hash and the original collector's later path-hash drift.

The production memory runner's post-measurement census calls `.values()` and thus
promotes full candidate indexes. Its shallow index totals count only the candidate carrier, omitting its internal
backing lists/dictionary, so they are not candidate storage accounting. Separate primary inventory
and inspection-before-census screens record actual compact capacities and costs.

## Mapping and artifact design

The previous prototype's equivalent-numeric-key miss is corrected by dictionary
promotion for non-exact-int operations. Native dictionary iterators/views handle
size changes, deletion/reinsertion, value updates, `.mapping`, reverse iteration,
last-in `popitem`, live wrappers and snapshot copies. The initial value-equivalence differential screen covers
numeric equivalents, fractions, int subclasses, custom equivalent/colliding keys,
unhashable keys, missing defaults, out-of-order insertion, negative/huge IDs,
10,000 seeded mutations and independent namespaces. A later custom-hash screen
finds six further counterexamples, including read-only proxy equality with an integer-
equivalent key held only by the other dictionary. These remain failures of the
measured candidate; a separate unmeasured native-delegation subclass resolves them. It also records conversion and
promotion overlap rather than counting borrowed keys or already shared origin values
as new savings.

Unpromoted storage has a dense reference list, insertion-order key list and sparse
fallback dictionary. Array growth is bounded by both four references per current
entry (minimum 64 allowance) and an absolute logical array length of `2**20`; shallow bytes include Python list spare capacity. Deletion promotes
and releases compact lists; native dictionary capacity behavior thereafter is retained.
Sparse-only workloads pay additional order-list overhead. These are explicit tradeoffs,
not a claim of universal superiority over dictionaries.

Production artifacts are schema **7**, correcting Task 07's stale schema-5 prose.
The isolated candidate uses schema **8008** plus source/probe fingerprints. Artifacts
are regenerated for each candidate and cannot be loaded by the unchanged production
codec. Compact rows use the same postorder object/reference mechanism as dictionary
rows, without creating full dictionaries during export or decode. Distinct mapping
proxies reference one serialized backing object. A promoted backing emits ordinary
dictionary rows, still memoized once. Invalid compact payloads, pair shapes,
noninteger/duplicate keys and unsupported backing classes are rejected. Existing
publication uses a temporary file and reports success only after replacement.

This remains the private source-coupled experiment: exact Python version and source
matching, trusted local symbols, and existing feature exclusions still apply. There
is no migration, format hardening or parked pre-compilation implementation here.

## Repeated results

[Raw build matrix](evidence/08-build-runs.json): five normal and three separately
traced processes per variant. [Summary](evidence/08-summary.json) also verifies
record/step/resolution signatures. All figures below are medians; MiB = 2**20 bytes.

| Eight routes, reduced metadata | Baseline | Origins only | Decorators only | Both |
| --- | ---: | ---: | ---: | ---: |
| Build, seconds | 11.641 | 11.692 | 11.590 | 11.638 |
| Cold resolution, ms | 14.944 | 15.115 | 14.980 | 14.752 |
| Retained Python, MiB | 3.098 | 3.099 | 3.099 | 3.099 |
| Traced build peak, MiB | 72.844 | 69.202 | 71.493 | 67.851 |
| Current RSS after build, MiB | 130.438 | 122.188 | 128.281 | 119.734 |
| Process peak RSS, MiB | 130.438 | 122.188 | 128.281 | 119.734 |
| Physical records / distinct steps | 8,982 / 1,765 | Same | Same | Same |

Both indexes lower traced peak **4.993 MiB / 6.85%** and normal RSS median
**10.703 MiB / 8.21%**. RSS ranges are separated: baseline 128.781–132.125 MiB,
both 117.938–121.672 MiB. Build ranges overlap: baseline 11.336–11.679 s,
both 11.556–11.790 s. The −0.003 s median difference is **no established speed win**;
the previous Task 07 +2.1% penalty is not reproduced with this refined fast path.
Short cold-resolution samples have no demonstrated regression. Runtime retention
is unchanged after successful reduction. Origins-only and decorators-only are
independent attribution controls, not additive RSS-saving estimates.

[Full metadata](evidence/08-full-runs.json), three normal/three traced processes
per candidate, retains **38.432→33.523 MiB** Python allocations, with build peak
**73.569→68.661 MiB**, and current/peak normal RSS **135.922→125.219 MiB**.
Build median is **11.110→11.283 s / +1.55%**, with overlapping ranges; cold resolution
is 22.665→22.822 ms. Full records/steps remain 88,558/1,765. This demonstrates
full-mode retention savings as well as compilation savings; the ordinary inspection
screen leaves the indexes compact.

[Diagnostics](evidence/08-diagnostics-runs.json) is a bounded **two-route** control,
not an eight-route production estimate: build 0.301→0.319 s, retained Python
0.607→0.607 MiB, traced peak 7.307→7.242 MiB and RSS 51.953→51.641 MiB.
It shows little absolute memory benefit and a +5.9% median build cost at that size.
[Two-route failed final validation](evidence/08-failure-runs.json) preserves root,
issue, manifest and selected-decorator witnesses: retained published Python evidence
1.080→1.014 MiB and traced peak 2.438→2.366 MiB, with unchanged ~45.23 MiB RSS.
Both have three normal and three traced runs. Failure timings are 0.324→0.318 s;
no failed-build speed improvement is established.

## Storage, lookup, conversion and inspection

The separate [primary inventory](evidence/08-inventory-both.json) confirms:

| Index | Entries / unique values | Baseline shallow backing | Compact owned backing |
| --- | ---: | ---: | ---: |
| Origins | 88,558 / 45 | 5,242,960 bytes | 1,424,048 bytes |
| Decorator explanations | 56,522 / 56,522 | 2,621,528 bytes | 1,293,712 bytes |

Dense logical lengths are 88,559 and 88,508; neither has sparse entries. Origins
retain increasing key order; decorator insertion order remains nonnumeric. The
combined **4.908 MiB** shallow reduction charges list spare capacity and the sparse
backing once, excluding borrowed integer/value referents. It is storage accounting,
not total recoverable RSS or an extra saving to add to traced peak reduction.

[Scaling/storage screen](evidence/08-storage.json), 1,000/10,000/100,000 entries
across five shapes, records construction/lookup/iteration costs independently.
At 100,000 entries, dictionaries use 5,242,960 shallow bytes; compact dense/gapped/
reverse maps use 1,602,096 / 4,093,776 / 2,031,016 bytes. Negative-only and huge-only
maps use **6,044,064 bytes / +15.3%**, because the sparse dictionary is accompanied
by an order list. These shapes remain bounded; no key is renumbered. The
[extended small-map screen](evidence/08-storage-extended.json) preserves the first
screen and additionally shows empty/singleton/ten-entry compact overhead:
240/288/496 bytes versus dict 64/224/352 bytes. At 100 dense entries it reverses:
1,968 versus 4,688 bytes. A small/sparse dictionary fallback policy needs review.

Untraced 100,000-key `.get` batches take **2.6–3.2×** dictionary time in the first
screen. Raw ordered iteration also costs more, and public iteration first pays
promotion. This is a narrow observer-process microcheck, not a claim that compilation
or every inspection becomes three times slower. The integrated build comparisons
above are the relevant compiler timings.

[Conversion/promotion screen](evidence/08-mapping-checks.json) constructs an
88,558-entry replacement while retaining the existing source dictionary. Newly
traced compact storage is ~1.424 MB; the source's 5.243 MB dictionary is outside
that tracer and remains held. Conversion takes ~0.16 s in that traced screen.
Promotion takes ~0.025 s and reaches **9,288,632 newly traced bytes** at its peak,
ending with ~5.243 MB dictionary storage. This explicitly demonstrates overlap,
not an integrated saving. Direct compilation has no whole-map conversion phase.
After deletion, compact lists release their capacity; native dictionaries retain
the same deleted-entry capacity behavior as the reference dictionary.

[Inspection before census](evidence/08-inspection-baseline.json) and
[candidate](evidence/08-inspection-both.json) are single observer screens. First
128-component explanation batches take 91.7→96.7 ms; repeats 26.2→26.4 ms.
First manifests take 547.8→539.3 ms, with cached repeats below 0.05 ms. Capacities
are unchanged before/after both passes, fingerprints match, and callbacks are not
replayed. These single-process timings do not establish a small inspection regression
or improvement. Public mapping view creation is a different operation: it permanently
promotes, removing compact retention savings for that index.

## Experimental artifact costs

[Artifact matrix](evidence/08-artifact-runs.json) has **48 fresh processes**:
three normal and three traced export/load processes per full/reduced candidate.
Loading disables compiler construction/building. Both modes preserve resolution
results and graph/step counts; all full fingerprints agree. Publication/rejection
checks preserve an existing output and remove temporary files after unsupported
backing/value failures. Backing sharing and ordered negative/huge-ID codec rows
also survive the focused roundtrip.

| Full artifact | Schema-7 baseline | Compact schema-8008 probe |
| --- | ---: | ---: |
| Artifact bytes | 29,484,023 | 29,484,349 |
| Export after compilation, seconds | 1.641 | 1.675 |
| Export retained Python, MiB | 38.447 | 33.538 |
| Export traced peak after reset, MiB | 85.413 | 80.505 |
| Export current / cumulative peak RSS, MiB | 148.562 / 160.172 | 140.203 / 151.828 |
| Fresh-process load, seconds | 1.181 | 1.275 |
| Load retained Python, MiB | 38.060 | 33.152 |
| Load traced allocation peak, MiB | 66.535 | 60.619 |
| Load current / peak RSS, MiB | 94.703 / 118.828 | 87.422 / 111.250 |

Full export rises **2.1%** and full load **8.0%** at the normal medians. Direct
encoding retains the memory benefit without keeping duplicate full dictionaries:
export peak falls 4.908 MiB traced / 8.344 MiB RSS, and load peak falls 5.916 MiB
traced / 7.578 MiB RSS. Artifact size changes only by representation/fingerprint
header bytes; it is **not** an artifact-size optimization. Export tracing resets
peak after compilation, so that column measures export live memory; process peak
RSS remains cumulative and is not reset.

Reduced artifacts contain no retained origin/decorator indexes. Size is
2,470,435→2,470,751 bytes; export 0.159→0.152 s, load 0.1121→0.1122 s.
Loader retained/peak Python is ~3.010/~5.940 MiB for both, with current RSS
48.531→48.109 MiB and peak 49.531→49.062 MiB. There is no demonstrated reduced
loader memory/time benefit; lower exporter RSS reflects the compile footprint.

Artifact resolution samples run **after census/manifest**, so they are not cold
resolution measurements and must not be compared to the clean build runner's
cold-resolution column. The matrix still verifies ordinary/managed providers,
maps, transient/scoped/singleton ownership and returned application results. A
future integrated refinement should place artifact cold resolution before inspection.

## Compatibility, checks and limitations

The measured candidate fixes Task 07's numeric-equivalent lookup, live view/
mutation/ordering gaps and all eight artifact failures. All **18 artifact tests**
and all **2,132 repository tests/executable examples** pass. The existing artifact
test's own unmodified subprocess remains a baseline process; the separate 48-process
matrix explicitly exercises the candidate's loader in independent processes.

Full/reduced source-attribution/multiplicity, normalized decorator facts, callback
counts/order, failure witnesses and all sixteen Task 06 opaque-value lifetime cases
match. Existing tests cover generics/aliases, boundaries, scopes/overlays, warmup,
profiling, budgets, build rules, cleanup, providers and maps. There is no callback
replay, lifetime/cache weakening, occurrence renumbering or provenance inference.

The stronger [custom-hash counterexamples](evidence/08-hash-counterexamples-with-refinement.json)
find **six remaining mapping failures** in the measured candidate. Five concern
inherited generic helpers; one reaches read-only proxy equality even though
stored keys are all integers. The separate native-delegation subclass matches native
outcomes/hash counts for all six. It is **unintegrated and unmeasured**, and its codec/
full-suite integration is not claimed. Passing ordinary tests cannot erase these
counterexamples. `clear` and remaining generic operations require the same deliberate
native-delegation audit rather than reliance on ABC defaults.

Focused **106 tests** plus differential mappings pass on CPython **3.11.13,
3.12.11 and 3.13.5**; full-suite/performance work uses **3.14.4**. Older interpreter
checks reuse pure Python dependencies with plugin autoload disabled, and compile the
prepared source outside any performance comparison when matching bytecode is absent.
Python 3.15-dev and other implementations/platforms are unavailable and unvalidated.
These are synthetic macOS measurements, not production application capacity estimates.

Repository Ruff lint/format, `ty check`, executable documentation validation and
BenchBro discovery pass. New executable probes pass format, type and byte-compilation
checks; explicit probe lint exempts E501 for generated source literals. An early
annotation-check failure is preserved and corrected, with no production edits.
The full-suite warning is the existing Starlette/httpx deprecation. Source verification
and the evidence index record unchanged production/test/benchmark sources.

## Recommendation and bounded follow-up

**REFINE. Do not implement the measured class as-is.** Its memory benefit survives
numeric/view/artifact fixes, and ordinary compiler behavior/inspection is preserved,
but proxy equality still has an observable custom-key failure. The native-delegation
feasibility result supports keeping the direction instead of dropping the idea.

The next scoped proposal is:

1. Keep graph-local exact integer insert/update/get storage, original key/value
   identity, insertion order and bounded dense/sparse capacity. Preserve all origin
   values verbatim; no definition-level provenance compression.
2. Integrate native dictionary delegation for public equality/copy/views/unions and
   generic mutable operations, including `setdefault`, `pop`, `update`, and `clear`.
   Alternatively document and review a strict internal integer API with a complete
   read-only adapter; integer-only writes do not excuse the public equality failure.
3. Choose an explicit small/sparse fallback policy. The measured zero-to-ten-entry
   and sparse-only regressions are concrete, not hypothetical. Avoid whole-map
   conversion at large graph completion or retained duplicate dictionaries.
4. Keep the private codec's identity-memoized backing record and direct compact
   decoding. Regenerate its source-coupled artifacts after any candidate change.
   Do not expand unsupported artifact features or the parked pre-compilation work.
5. Run the six counterexamples, mapping/view/lifetime/graph checks, all eight former
   artifact failures and the full suite on the integrated refinement, followed by
   five normal/three traced same-source compiler processes and three normal/three
   traced full/reduced export/load processes. Measure artifact cold resolution
   before inspection and report promotion costs separately.

**Implementation readiness: not ready** until that complete adapter is integrated
and remeasured. Storage/sparsity thresholds and promotion costs require an explicit
acceptance decision; the measured class is not approved merely because production
readers currently use integer IDs. No cache, slots, production implementation,
commit, push or pre-compilation work is included.

## Reproduction

Run commands serially without a competing test/benchmark workload:

```sh
.venv/bin/python .work/graph-memory-optimization/evidence/08-probe.py prepare
.venv/bin/python .work/graph-memory-optimization/evidence/08-run.py --suite build
.venv/bin/python .work/graph-memory-optimization/evidence/08-run.py --suite full
.venv/bin/python .work/graph-memory-optimization/evidence/08-run.py --suite diagnostics
.venv/bin/python .work/graph-memory-optimization/evidence/08-run.py --suite failure
.venv/bin/python .work/graph-memory-optimization/evidence/08-run.py --suite artifact
/bin/sh .work/graph-memory-optimization/evidence/08-checks.sh
.venv/bin/python .work/graph-memory-optimization/evidence/08-hash-counterexamples.py
.venv/bin/python .work/graph-memory-optimization/evidence/08-summarize.py
```

The archived v2 probe reproduces the initial matrix's exact source hash; current
v3 has identical AST/executable behavior and a type-check suppression comment.
All prepared source/bytecode hashes are checked at load. Generated artifacts remain
locally in `.cache/graph-memory-task08/`; their hashes/sizes are recorded separately.
The original Task 07 evidence and the preliminary/failed-check Task 08 evidence are
preserved. The native-delegation subclass is only in the hash-counterexample helper;
no compiler or artifact matrix installs it.

