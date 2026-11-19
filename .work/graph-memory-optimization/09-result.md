# Task 09 — compact indexes with native delegation and bounded fallback

Status: Complete — isolated prototype retained, 2026-10-09. GPT-6.1 Sol, medium reasoning.
Production adoption: not ready; scoped verification complete and suitable for implementation review.
Production sources remain unchanged; no commit, push, cache/slots combination or
parked pre-compilation work is included.

This is an isolated compiler/codec candidate. The exact class installed into both
paths fixes the six original custom-hash counterexamples. General mapping methods
now delegate directly to native dictionaries rather than ABC helper methods.
The [boundary inventory](09-inventory.md) defines the private typed index and its
live read-only adapters; it does not create a public origin-map API.

## Final candidate and evidence identity

The final measured probe SHA-256 is
`95048c57af51588e8e47cd69f06459c6e5101245930f216720ab4db002763962`.
[Prepared source/bytecode hashes](evidence/09-prepared.json) and
[driver/fixture hashes](evidence/09-driver-identity.json) identify the final
comparison. Original production sources match `d51b6f5`; HEAD is `7b9a841`.
The same loader consumes prepared bytecode for controls and candidates. Runtime
source/bytecode hash checks reject changes. Preparation occurred outside measured
processes. Python 3.14.4, macOS ARM64; unchanged rich eight-route fixture,
`allow_scope_builders=False`, diagnostics off except bounded diagnostic controls.
Caller builders/selection views are not retained in ordinary comparisons.

The [preliminary policy](evidence/09-preliminary-probe.py.txt) rejected the early
decorator index before it became dense. Bounded geometric reconsideration fixes
that loss. An additional signature audit found get/setdefault/pop keyword-key
acceptance inconsistent with native dictionaries; positional-only signatures were
added. Earlier [partial measurements](evidence/09-preliminary-build-runs.json) are
archived and excluded. Initial null-state type diagnostics are preserved in
[evidence/09-preliminary-typecheck.txt](evidence/09-preliminary-typecheck.txt);
explicit private state annotations fix them without adding measured assertions.
An expected broken-pipe message came from interrupting the preliminary runner;
final checkpoint JSON belongs only to the final probe hash.

## Fallback and adapter decisions

The [policy screen](evidence/09-policy-checks.json) compares thresholds 32, 64,
128 and 256 across empty/tiny, dense, gapped, reverse, negative, huge and mixed
shapes. Threshold 128 is a conservative starting point, not a proven optimum.
Density is reconsidered only at six checkpoints through 4096 entries; there is
at most one small native-to-compact conversion. Initial/sparse maps retain a
native dictionary plus **72 bytes** of carrier, with no order/array/sparse-container
allocation. Thus empty storage is 64→136 bytes and ten entries 352→424 bytes.
At 128 dense entries, shallow storage is 4688→2296 bytes; at 10,000 dense entries
294992→170488 bytes. Gapped/negative 10,000-entry maps are 294992→295064 bytes.
The earlier sparse-only percentage regression is replaced by fixed carrier cost.
This deliberately forgoes savings for maps whose insertion order becomes dense
only after the last checkpoint.

Compact growth uses a two-times-entry density bound and `2**20` absolute logical
array length. More than `max(32, entries // 8)` sparse entries permanently promotes
that carrier and releases compact storage. Deletion and general operations also
promote permanently. Existing views lock one native dictionary; clear and later
growth never replace it. Native copies/equality/update/unions preserve stored
hashes. Integer fast paths preserve original key/value identities and insertion
order. Borrowed keys/shared origins are counted once; no provenance compression or
whole-graph completion conversion occurs.

Promotion remains a measurable cost: the 88,558-entry differential screen holds
an external source dictionary while constructing/promoting its replacement. That
source dictionary is outside the new tracer and remains live. Promotion's new
traced peak is around **8.9 MiB**, not a net process saving. Public raw mapping
views/copies/equality can permanently relinquish compact savings. Ordinary graph
explanations/manifests use indexed reads and are checked separately for promotion.
These costs are accepted for the scoped prototype, with production decisions below.

## Measurements and verification

The final matrix contains **104 distinct fresh processes**: 16 reduced compiler,
16 full compiler, 12 diagnostic, 12 failure and 48 artifact export/load processes.
Every result carries the same final probe hash; controls and candidates use the
same prepared loader. No competing test/benchmark workload ran during the matrix.
[Final verification](evidence/09-final-verification.json) checks unique PIDs,
source identity, semantic equivalence and artifact headers. Normal/traced groups
remain separate; these local synthetic measurements do not establish production
capacity or a formal timing significance claim. Filesystem caches are not flushed;
“cold” resolution means a fresh unresolved runtime, not cold disk I/O. The unchanged
runner's offline census creates `.values()` views and promotes full candidate indexes
**after** memory/cold-resolution observations. Its shallow index counts omit internal
backing storage and are not used as storage accounting here; separate raw-capacity
inventory/inspection screens provide that evidence.

## Final compiler comparison

Medians from five fresh normal and three separate traced processes per variant.

| Measurement | Reduced baseline | Reduced candidate | Full baseline | Full candidate |
| --- | ---: | ---: | ---: | ---: |
| Build seconds | 11.426 | 11.477 | 11.717 | 11.841 |
| Cold resolve milliseconds | 14.999 | 15.047 | 25.238 | 25.305 |
| Retained Python MiB | 3.098 | 3.098 | 38.431 | 33.474 |
| Traced build peak MiB | 72.844 | 67.887 | 73.568 | 68.611 |
| Current RSS MiB | 130.812 | 121.078 | 135.422 | 125.859 |
| Cumulative peak RSS MiB | 130.812 | 121.078 | 135.422 | 125.859 |

Reduced traced peak saves **4.957 MiB**; full retained Python saves **4.957 MiB**.
Normal build medians rise 0.45% reduced / 1.06% full, with overlapping observed
ranges (reduced 11.325–11.573 vs 11.369–11.589 s; full 11.537–12.020 vs
11.726–12.193 s). This does not establish a build-time regression. Cold resolution
is essentially unchanged in these samples. Current RSS saves 9.734 MiB reduced /
9.563 MiB full. Do not compare these same-source controls with old task baselines.

Full graphs retain 88,558 physical records and 1,765 distinct execution steps;
reduced graphs retain 8,982 physical records and the same steps. Logical visits
are unavailable in reduced mode. Compilation occurrence IDs, callbacks and
resolution values match controls. Tracing reports Python allocations; RSS is
the entire process and the cumulative peak cannot be reset.

## Experimental artifact comparison

Three normal and three separately traced export/load processes per mode/variant.
Artifact cold resolution precedes census/manifest; compiler construction/building
is disabled in loader processes. Backing identity survives compact, fallback and
promoted rows. [Artifact files and hashes](evidence/09-artifact-files.json) describe
regenerated files under `.cache/graph-memory-task09`; Task 08 files are untouched.

| Full artifact measurement | Schema-7 baseline | Schema-8009 candidate |
| --- | ---: | ---: |
| Artifact bytes | 29,484,023 | 29,484,349 |
| Export seconds | 1.707 | 1.935 |
| Export retained Python MiB | 38.445 | 33.488 |
| Export traced peak MiB | 85.412 | 80.454 |
| Export current RSS MiB | 145.109 | 139.953 |
| Export cumulative peak RSS MiB | 156.766 | 151.703 |
| Load seconds | 1.203 | 1.363 |
| Load retained Python MiB | 38.060 | 33.103 |
| Load traced peak MiB | 66.535 | 60.619 |
| Load current RSS MiB | 94.828 | 89.203 |
| Load peak RSS MiB | 118.969 | 112.719 |
| Export cold resolve milliseconds | 24.534 | 27.415 |
| Load cold resolve milliseconds | 20.772 | 22.988 |

Full export rises **13.39%** and full load **13.27%** at these normal medians.
Export ranges are 1.705–1.722 vs 1.804–2.229 s; load ranges 1.201–1.492 vs
1.344–1.441 s overlap because of one slower control. The observed startup penalty
is material; Task 08's old ~8% load figure is not reused. Full artifact cold resolve
medians rise by 2.9 ms export / 2.2 ms load, with overlapping observed ranges.
Compiler cold resolution remains essentially unchanged. Do not turn these small
samples into a universal runtime regression estimate.

The memory benefit survives: full export retains/peaks ~4.96 MiB less traced
memory; full load retains 4.96 MiB less and peaks 5.92 MiB less. Full loader RSS
falls 5.625 MiB current / 6.250 MiB peak. Export's traced peak resets after
compilation; its process peak RSS stays cumulative. Encoding/decoding does not
retain duplicate full dictionaries, and backing memoization is preserved.
Artifact size rises 326 bytes; this is not an artifact-size optimization.

Reduced artifacts are 2,470,435→2,470,751 bytes; export 0.1668→0.1595 s and load
0.1146→0.1201 s. Both load retention and peak remain ~3.010/~5.940 MiB.
Normal reduced loader current RSS is 48.203→49.453 MiB and peak 49.156→49.766 MiB;
there is no demonstrated reduced-loader memory benefit. Reduced loader cold
resolve is 13.104→14.614 ms. Lower reduced exporter RSS reflects compilation's
footprint, not retained artifact indexes.

## Operation, inspection and transition screens

[Mapping differential](evidence/09-mapping-checks.json) passes over 10,000 checks,
including numeric equivalence, original key/value identity, ordering, live views,
iterator invalidation, snapshot copies, defaults/errors and graph-local namespaces.
The [103-case audit](evidence/09-operation-audit.json) adds native methods/unions,
initial/compact/promoted states, shared codec backing and raising-equality callback
counts/outcomes. All [six original hash counterexamples](evidence/09-hash-counterexamples.json)
match native outcomes/hash counts in the exact class installed into compiler and
codec, including integer-only proxy equality with an equivalent foreign key.
This is verified alongside integrated compiler/artifact/full-suite checks, not
merely a passing standalone subclass.

[Storage/lookup screen](evidence/09-storage.json): 100,000 dense entries use
5,242,960→1,602,104 shallow bytes, with **3.00×** native get time in the narrow
observer loop. Gapped/reverse/negative/huge indexes use native fallback plus
72 bytes and **1.73–1.84×** native lookup time, paying the outer adapter call.
These narrow timings do not describe all compilation or runtime resolution.
The lookup penalty remains an explicit cost rather than a dismissed failure.

[Policy/transition evidence](evidence/09-policy-checks.json) includes native-to-
compact threshold and later-density transitions, dense-to-sparse promotion and
public promotion. Transitions are bounded and release compact containers. At
88,558 entries the differential promotion screen peaks at ~8.9 MiB newly traced
allocations and takes around 25 ms; its retained source dictionary is outside
that tracer. Neither this screen nor list capacity is a net RSS saving.

[Control inspection](evidence/09-inspection-baseline.json) and
[candidate inspection](evidence/09-inspection-both.json) preserve capacities before
and after bounded explanations, traversal and manifests; no promotion or
callback replay occurs. First 128-component explanation batches take 93.6→94.3 ms,
repeats 27.9→27.1 ms; first manifests 556.3→567.3 ms and repeats below 0.04 ms.
These single observer screens do not establish a small timing regression.
[Bounded diagnostic inspection](evidence/09-inspection-diagnostics-both.json) also
runs selection census twice, with unchanged capacities and matching control
fingerprint. Repeat inspection is measured separately. Public raw
mapping iteration/views/copy/equality promote permanently and lose the savings of
that index. This is accepted for the private adapter's uncommon general operations.
If applications retain/promote these maps routinely, this proposal provides less
benefit and must be reassessed.

## Semantic and repository verification

All **2,132 tests/executable examples** pass in 31.24 s; the one warning is the
existing Starlette/httpx deprecation. The **18 artifact tests** are included in
that final passing suite. Their existing unmodified subprocess remains a baseline
process; the separate 48-process matrix installs the candidate in fresh loaders. Full/reduced
semantic controls match step-source attribution/multiplicity, normalized decorator
facts, callbacks and failed-finalization witnesses. All **16 Task 06 opaque-value
lifetime cases** pass under explicit Task 09 loader provenance; their helper's
`baseline` option disables Task 06 cache patches. No cache proposal is combined.
Existing tests cover providers/maps, managed cleanup, aliases/generics, boundaries,
scopes/overlays, warmup, diagnostics, profiling, budgets and failure publication.
Atomic codec rejection preserves prior output and removes temporary files;
malformed/unsupported payloads are rejected.

Two-route diagnostic/failure controls use three normal and three traced processes
per variant. Diagnostic peak falls 7.307→7.241 MiB; failed-graph retention
1.080→1.014 MiB and peak 2.438→2.366 MiB. Build medians are 0.285→0.290 s
(diagnostics) and 0.284→0.291 s (failure). Failure fingerprints, roots, issue codes
and selected decorator witnesses agree. These bounded controls are not additive
savings or a large diagnostic-workload capacity claim.

Focused **106 tests per version**, mapping differentials, all six hash cases and
103-case audits pass on CPython **3.11.13, 3.12.11 and 3.13.5**. Full suite and
performance comparisons use **3.14.4**. Older runs use pure Python dependencies,
plugin autoload disabled and matching source compiled when prepared bytecode is
unavailable; those are unmeasured verification processes. Python 3.15-dev,
non-CPython implementations and non-macOS/ARM64 environments are unavailable.

Repository format, type checking, executable documentation and BenchBro discovery
pass. Explicit probe lint/format/type checks pass; bytecode preparation validates
syntax. Unmodified repository lint reports one **pre-existing E501** in preserved
Task 08 evidence at `08-hash-counterexamples.py:123`. A rerun with only that file's
E501 exemption passes; the earlier evidence is not edited. This raw failure and
narrow rerun are recorded separately. An initial policy-helper union annotation
error is preserved in `09-typecheck-initial-policy.txt` and corrected with an
explicit measurement-carrier annotation. Static checks cover repository sources
and prototype helpers; dynamic globals in transformed modules are a prototype
loader mechanism, not a completed production typing/interface design.

## Recommendation and readiness

**RETAIN the corrected isolated prototype for implementation review.** The six
compatibility blockers are repaired, artifact backing identity and captured facts
survive, and roughly 5 MiB of full retention/build peak savings remain in the
fixed eight-route workload. Do not drop this direction on the narrow lookup ratio
alone: observed integrated build/cold-resolution medians remain close to controls.

Accept the tested fallback/carrier policy for this scope: sparse-only percentage
overhead is replaced by 72 bytes per carrier, growth/conversions are bounded,
and reverse/late-density maps may deliberately stay native. Accept permanent
promotion and its temporary peak for exact native general operations on these
private sidecars. Accept the artifact startup cost for the prototype comparison,
while explicitly retaining the **~13% export/load penalty**, small observed cold
resolve differences and **~3× dense / ~1.8× fallback lookup cost** as constraints
on any application-level adoption decision. A startup-sensitive use case can
choose native indexes; no new public toggle is implemented here.

**Scoped verification is complete; production adoption is not ready/approved.**
There are no remaining observed correctness failures in the documented adapter
contract. A separate production implementation must place the typed class/adapter
in normal source, review ownership/API assumptions, accept startup/promotion costs
against representative application budgets and run its normal supported-platform
checks. Experimental schema 8009 is source-coupled evidence only, not a production
format/migration. This does not claim full `dict` replacement, production capacity,
or validation of every private third-party consumer. No production implementation,
commit, push, task 06 cache optimization, task 07 object-layout change or parked
pre-compilation feature is included.

## Reproduction

Run serially without competing test/benchmark workloads:

```sh
.venv/bin/python .work/graph-memory-optimization/evidence/09-probe.py prepare
/bin/sh .work/graph-memory-optimization/evidence/09-pipeline.sh
```

The pipeline runs all final measurement groups, summary and checks. It preserves
raw repository lint and applies only the known prior Task 08 E501 exemption.
`09-final-checks.sh` reproduces the post-measurement static/supported-Python checks.
[Evidence index](evidence/09-evidence-index.json) records final probe/evidence hashes;
[production-source verification](evidence/09-source-verification.json) and the empty
[production diff](evidence/09-production-diff.txt) confirm unchanged shared sources.
All previous evidence and preliminary Task 09 runs are preserved separately.
