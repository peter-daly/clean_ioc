# Task 03 result — reachability audit, pruning declined

Completed: 2026-10-08\
Status: Complete — audit retained; production pruning declined\
Implementation agent: GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning\
Decision: Retain the offline audit and decline a production pruning pass. No
compiler, runtime, graph representation or artifact codec change was made.
All verification and the unchanged-runtime confirmation are recorded below.

## Reachability and the removal boundary

The [offline audit](../../benchmarks/graph_reachability_audit.py) uses pairs of
(graph identity, occurrence identity), not occurrence integers alone. Its closure
follows dependencies, decorators, pre-configurations, parent, decorated and owner
links. Negative provider-view identities resolve through their context to the
physical source and context parent, then retain the projected logical links.
Every stored edge is validated independently, even outside executable roots.
It traverses captured library dataclasses and built-in containers, never calling
application constructors, predicates, factories, equality, hashing or repr.
Origins alone are bookkeeping, not a liveness root. Captured compact-pattern
original IDs remain provenance; authoritative occurrence wrappers and sidecar
owners provide graph context, rather than interpreting original IDs as remapped
execution links.

The [eight-route audit](evidence/03-audit-verified.json) classifies all 88,558
records. Counts are physical records in the runtime's primary graph. Public
traversal visits and negative contextual-view IDs are separate observations.

| Disjoint category, in precedence order | Records |
| --- | ---: |
| Public roots and complete relationship closure | 8,932 |
| Additional execution / provider / managed / architecture / warmup roots | 50 |
| Additional eligible or rejected root-candidate evidence | 0 |
| Additional explanation-owner evidence and relationship closure | 79,576 |
| Additional contextual-view source / parent records | 0 |
| Outside every audited root | 0 |

The overlapping groups make the root accounting reviewable: ordinary provider
roots reach 632 primary records (3,032 logical IDs); managed-provider roots reach
8,958 (17,890 logical IDs); execution components, including map targets and
compiled resolution requests, reach 8,932 physical records; eligible root-candidate
closure reaches 8,964; all contextual-view source/parent closure reaches 8,982.
The fixture has no warmup or independent boundary roots and no rejected root
candidates. Added audit tests exercise warmups, unexposed boundary architecture
roots and inherited anchored execution graphs separately.

The 79,576 records outside runtime-root closure comprise 48,608 registrations,
30,408 values and 560 decorators. They are candidate/intermediate contextual
records retained by sidecars, not 79,576 proven garbage records. Merely retaining
an explanation-owner key does not prove that its component must stay: pruning
could conceivably remove unreachable sidecar entries together. Conversely,
physical-record/execution-step and public-traversal differences cannot prove
that a record is safe to remove.

A removal boundary would have to exclude the closure of *all* public/runtime
roots, execution-held Components (including inherited graph references), candidate
and inspection roots, provider-view sources/parents, and externally retained
callback Components. Sidecars would need consistent coordinated pruning while
preserving every supported captured fact. Full diagnostics additionally require
truthful rejected decisions and existing census attribution. No pass may run on
failed/partial compilations before their evidence is copied: `partial_attempt`
captures up to 500 structural records plus separately retained edges/candidates,
with explicit truncation, including discarded and failing work. Failed final
validation can also expose the compiled graph. A hypothetical successful-only
pass would therefore run after final validation, warmup planning and all required
failure evidence boundaries; it cannot change those contracts.

## Concrete reason to decline pruning

The compiler does not inventory Component views that escape into application
callbacks. Selection predicates may retain the actual read-only Component they
receive, including a rejected dependency candidate and its contextual ancestors
and descendants. Later inspection of those views currently works. Graph-local
metadata-key deletion can break that behavior even when ordinary root traversal
and runtime resolution still succeed. Referrer scans of arbitrary application
objects are neither a reliable proof of absence nor a suitable build-time policy.

The [forwarding-predicate experiment](evidence/03-audit-verified-escaped.json)
wraps the rich fixture's built-in `with_name` predicate, stores the supplied
Component, and forwards selection to the original predicate. At two routes, 20
callback views escape. Their closure requires **600 primary-graph records outside
all runtime-root closure**, and reaches two additional source-inspection graphs.
All links resolve, and the escaped views remain inspectable after build. This is
a concrete counterexample to pruning from executable/public roots alone, not a
claim that every eight-route intermediate has escaped. The audit accepts explicit
external roots for this experiment; it does not claim to discover arbitrary
external references automatically.

A conservative policy protects captured sidecar-owner closures as well as normal
roots. Under that policy the audited eight-route removable set is empty. Relaxing
it would require a new escape/snapshot or graph-retention design and additional
compatibility work, rather than deleting metadata on the assumption that rejected
work has no observers. That design is outside task 03. No diagnostic evidence,
filter/callback behavior, graph inspection or task 04 was weakened to obtain a
saving. The original task 01/02 implementation and artifact experiment remain
intact and uncommitted.

## Audit cost and unchanged-runtime measurements

The audit is an explicitly invoked benchmark utility, absent from compilation,
resolution and public inspection. A fresh eight-route normal observation takes
0.762 seconds. A [separate audit-only traced observation](evidence/03-audit-verified-traced.json)
takes 5.257 seconds, peaks at 80,832,772 bytes (77.09 MiB) of temporary traced
allocations, and retains 10,282 bytes including its result after collection.
Tracing begins after compilation, so these are audit costs, not whole-build
peaks or total graph memory. The conservative closure keeps multiple temporary
sets; this is not proposed production machinery. Net production memory benefit
is **zero**; production build/peak/runtime/inspection costs are unchanged.

[Before](evidence/03-before.json) and [after](evidence/03-after.json) use eight
routes, diagnostics disabled, three fresh normal processes and three separate
traced processes each. They run serially without tests or other benchmark
workloads. Tracing begins before fixture import, and retained memory follows
collection. Census and validation are outside timed build/resolution intervals.
The after group is an unchanged-runtime confirmation, not an implemented pruning
A/B comparison. Source hashes in each sample document the unchanged compiler,
components, tooling, census and fixture. The original baseline, tasks 01/02 raw
evidence and artifact retest evidence were preserved.

| Measurement | Fresh baseline | Unchanged-runtime confirmation |
| --- | ---: | ---: |
| Fixture import, composition and build | 11.278 s | 11.405 s |
| Resolution workload | 23.90 ms | 23.69 ms |
| Current / peak RSS after build | 133.83 MiB | 133.23 MiB |
| Retained traced allocations after build | 38.43 MiB | 38.43 MiB |
| Build traced allocation peak | 73.58 MiB | 73.58 MiB |
| Current / peak RSS after resolution | 133.83 MiB | 133.23 MiB |
| Retained traced allocations after resolution | 39.55 MiB | 39.55 MiB |

The [comparison ledger](evidence/03-comparison.json) confirms identical measured
source hashes across all twelve processes and identical graph/metadata counts,
callback counts, activation counts and resolution validation. Both groups retain
88,558 physical records, 1,765 execution steps and 116 shared definitions. The
63-byte retained-allocation difference is bookkeeping-scale noise, not pruning
savings; timing and RSS variation have no changed production implementation to
attribute them to. The recorded revision is `31f1682075b2c146de7672fa37cb5fb563a0ffc7`
with all previous local uncommitted changes preserved.

The diagnostics-enabled [two-route audit](evidence/03-audit-verified-diagnostics.json)
also finds no missing links and classifies 2,368 records: 1,264 public-closure,
14 additional runtime-root, 1,090 additional evidence-closure, and zero outside
all audited roots. No 32-route attempt was made. Measurements remain synthetic,
local Python 3.14.4/macOS ARM64 observations.

## Verification and remaining scope

The [final check log](evidence/03-checks-final.json) records all 2,079 tests
passing, including six added audit cases. Ruff lint/format, type checks, docs
examples and benchmark discovery pass. Strict MkDocs reproduces exactly the same
eight existing links-to-files-outside-docs warnings; the existing FastAPI/Starlette
deprecation warning remains. Initial audit-only lint/type findings were corrected;
the [first check log](evidence/03-checks.json) is preserved rather than overwritten.
The complete suite includes public selection/filter/traversal/ownership, diagnostic
census and failed-build evidence, ordinary/managed providers/maps, boundaries,
overlays, warmups, profiling and the schema-5 artifact compatibility tests.

A separate [public inspection observation](evidence/03-inspection.json) preserves
8,932 traversal visits and the task-02 fingerprint
`fa06427a9c823d18961ba2d173294ce206f38c516f2478dd229e7d1bebaaa722`
on first and repeated manifest access. First/repeated explanation sampling of
128 components takes 102.3/27.8 ms; public traversal takes 94.4/94.4 ms; manifest
creation/cached access takes 571.0 ms/0.015 ms. These are single traced inspection
observations, not repeat medians. Inspection never reruns template callbacks;
the existing membership/manifest caches and their retention remain unchanged.

The evidence tool and compatibility tests are retained for review. Production
pruning is declined; task 03 completes its allowed audit/decline outcome. Task 04
remains planned. No commit, push, deployment or unrelated work was performed.
