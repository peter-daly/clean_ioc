# Item 23 — Unified slots result

Date: 2026-10-16  
Current API follow-up: `declare_slot(..., target=...)`; old alias and `scope=`
removed. Follow-up validation/review is complete: **APPROVE / KEEP**, 2,610 tests pass.
Details are recorded at the end. Initial evidence
below remains a historical record of the earlier API spelling.  
Implementation: GPT-6.1 Sol, high reasoning (`/root/unified_slots`)  
Independent review: GPT-5.6 Sol, high reasoning (`/root/unified_slots/review`)  
Baseline: `88a039ff7c1071d71ffccce24a859d23e76a9727`, branch `version2`  
Status: Implemented and independently reviewed — APPROVE / KEEP.

## Initial delivery contract (superseded API spelling)

`declare_slot(T, scope="container"|"scoped", name=..., tags=..., binding=..., when=...)`
now works in ordinary builds. `provide(..., binding=...)` supplies caller-owned
instances without changing compiled selection. The old `declare_scope_slot()`
shorthand remains idempotent, including inherited identical scoped declarations
in overlays. Canonical aliases use the same input identity.

Conditional slots require explicit nonempty string bindings. Compatible views can
share one binding; scalar, collection and map selection deduplicate matching
views of that input. Duplicate implicit identities, implicit/explicit identity
conflicts across any view, duplicate unconditional views and incompatible
binding type/lifetime contracts fail before build success. Competing eligible
scalar dependency bindings fail with source-linked consumer/parameter evidence.
Names, tags and binding metadata survive execution projection; predicates and
explanation histories are not needed for runtime lookup.

Container inputs live on the root container, are shared by descendants and cannot
be overridden there. Scoped inputs retain inherited values and local overrides.
Readiness checks all required container bindings before activation, reports
missing bindings together, and leaves inputs open after failure. Successful
activation seals container input across descendants; scoped locks belong to each
supplying scope. Supplied instances are never entered or finalized by Clean IoC.
Singleton capture of scoped inputs stays a `verify()` policy finding, preserving
the execution-only `build()` contract.

Required inputs derive from frozen public roots, public/deferred provider targets
and warmups. Conservative internal managed adapters matter only when reachable
managed `ResolutionContext` execution can activate them. Private architecture-only
boundary roots do not introduce runtime requirements. Unconditional slots expose
ordinary roots/provider families; declarations without executable occurrences
remain optional. Container inputs can be direct warmup targets.

Registrations, including fallback registrations, keep precedence. Slots fill holes
in scalar, collection and callback-map selection. The documented intentional
extension is that scoped slots now fill otherwise empty collections; registered
collection cardinality is preserved. Provider/collection wrappers remain real
selection parents. Runtime root filters can still be passed dynamically; competing
slot roots selected by such a filter raise `ScopeProvisionError`.

Overlays may add scoped inputs and use inherited container inputs, but cannot add
new container inputs or reopen sealed ancestors. An overlay needing a previously
optional, unprovided sealed input fails clearly. Unconditional root slots can be
imported into boundaries; conditional imports and private boundary slots fail
with explicit unsupported errors.

Artifact export/loading, codecs, packaging and cross-process/consumer application
benchmarks are outside this item. No persistence implementation, push, release or
commit was performed.

## Changed implementation and documentation

- `clean_ioc/container.py`: frozen slot declarations/runtime inputs; unified API;
  binding contracts; contextual selection and ambiguity; root/provider/map/collection
  fallback; readiness capture and activation; container/scoped provision rules;
  overlay checks and compatibility shorthand.
- `clean_ioc/components.py`: typed builder protocol and frozen `slot_binding`
  inspection metadata; `clean_ioc/graph_analysis.py`: supplied input obligations
  distinguish container/scoped ownership and identify public bindings.
- `tests/test_unified_slots.py`: 77 parameterized cases across build and verification
  runtimes, sync/async, providers/maps, contexts, ownership, warmup, overlays,
  boundaries, aliases and observations. Existing alias collection expectations and
  one private-step construction case are updated for the deliberate extension/model.
- `docs/slots.md`: public contract with three executed examples; related scope,
  lifespan and warmup guides, site navigation, example validation and `CHANGES.rst`.
- Work-item/readiness records, independent review and cost evidence under `.work`.
  Prior work-item extraction edits were preserved.

## Validation

Final matrix commands use the locked project dependencies and separate temporary
Python environments; the normal `.venv` remains Python 3.14.4. `make ci` includes
Ruff, format checking, `ty`, the entire test suite, executable documentation and
BenchBro discovery. Exact final outcomes are recorded in
[23-validation.txt](23-validation.txt).

The final complete matrix, after all review fixes, passes:

| Python | Tests | Existing version skips |
| --- | ---: | ---: |
| 3.11.13 | 2,594 passed | 8 |
| 3.12.11 | 2,599 passed | 3 |
| 3.13.5 | 2,602 passed | 0 |
| 3.14.4 | 2,602 passed | 0 |

Each run has the existing FastAPI/Starlette `httpx` deprecation warning. Strict
MkDocs and `git diff --check` also pass. Final source hashes match the reviewed
and measured sources.

Independent review recommends **APPROVE / KEEP** in [23-review.md](23-review.md).
Six findings were fixed and independently retested: later shared-view identity
conflicts, boundary precedence, optional-input reachability, inherited shorthand
idempotence, observed-provider identity and source-linked declaration/root errors.
The final one-key-per-provision-lookup adjustment was also reviewed. Reviewer
checks include 77 slot cases, 331 broader focused cases and 92 slot/alias cases
for that last delta, plus static checks and executable/strict documentation.

## Focused cost evidence

[23-slot-cost.py](23-slot-cost.py) is the reproducible probe;
[23-slot-cost-evidence.json](23-slot-cost-evidence.json) contains the two final
before/after samples, source hashes and method. The original package was extracted
from the baseline commit into a temporary directory. Both sources use the same
Python 3.14.4 interpreter, dependencies and script on this host. Each sample has
seven repeats of 100 builds or 10,000 scope/resolution operations. Pair 3 runs
before/after; pair 4 reverses that order. Values below are repeat medians in µs.

| Probe | Baseline pair 3 → final | Baseline pair 4 → final |
| --- | ---: | ---: |
| Build without slots | 2751.453 → 3008.217 (+9.3%) | 2598.933 → 2984.287 (+14.8%) |
| Build one scoped slot and its consumer | 1503.830 → 3303.232 (+119.7%) | 1513.421 → 3259.235 (+115.4%) |
| Ordinary scope creation without slots | 0.908 → 0.919 | 0.929 → 0.926 |
| Warm ordinary consumer resolution without slots | 1.573 → 1.606 | 1.612 → 1.591 |
| Warm scoped-input consumer resolution | 1.574 → 1.652 | 1.583 → 1.654 |

There is material additional compilation cost in this small fixture. The slot
fixture now emits a public slot root/provider family as well as the consumer;
it previously emitted only a dependency hole. The no-slot compiler also pays for
the new component/input metadata and selection paths; these samples show a
0.26–0.39 ms construction increase. Scoped-input lookup adds roughly 0.07–0.08 µs.
Ordinary scope creation and no-slot warm-resolution differences vary in direction
and do not establish a meaningful runtime change. No performance saving or
zero-overhead claim is made.

These are focused host microprobes, without CPU isolation or a randomized
statistical benchmark. They do not estimate production startup, throughput or
RSS. Initial and intermediate samples are retained inside the evidence bundle as preliminary evidence;
only final samples 3 and 4 correspond to the reviewed final lookup code. No
application or whole-upgrade memory acceptance is inferred from correctness.

## Limitations and follow-on

- New container declarations in overlays, private boundary slots and conditional
  boundary imports are deliberately unsupported, with explicit errors and docs.
- Contribution-group provider maps still select registered contributors; slots
  do not declare group contributions. Callback-based maps support slot fallback.
- Default root collections of provider handles keep the existing explicit-filter
  requirement. Dynamic root-filter ambiguity is detected at resolution; compiled
  scalar dependencies are checked during build.
- Artifact task 01 consumes this frozen contract. Its format/loading prerequisites
  and implementation remain independent and unfinished.

## API follow-up — required target, no compatibility alias

The maintainer subsequently requested `declare_slot(T, target="scoped"|"container")`
and complete removal of `declare_scope_slot()` and the old `scope=` declaration
keyword. The implementation/protocol, all active Python callers, public docs,
upgrade guide and packaged skill references now use the required target keyword.
No runtime lifetime, ownership, selection or readiness semantics changed.

The old idempotent shorthand and its compatibility-only tests were removed.
Duplicate implicit declarations now fail uniformly, including inherited overlay
redeclarations. ASGI/FastAPI bundles retain their once-per-class guard on each
builder, including shared ASGI setup; overlays inherit root bundle inputs and
adapters without reapplying that bundle. Applying it to an overlay whose root
lacks that setup remains supported.

Tests explicitly check signatures/removal on ComponentBuilder, ContainerBuilder,
ScopeBuilder and BoundaryBuilder; target omission and both forms of the old
scope keyword raise TypeError. Duplicate overlay declarations and actual bundle
flows are covered. The current slot suite has **83 cases**, and focused slot plus
ASGI/FastAPI checks pass **104 tests**.

Final Python 3.14.4 `make ci` exits 0 with **2,610 tests passing** (one existing
FastAPI/Starlette warning), including lint/format/typing, executable docs and
benchmark discovery. Strict MkDocs and diff checks pass. Focused independent
[review](23-target-review.md) recommends **APPROVE / KEEP** with no open findings;
the stale marketing demo it found was fixed and rechecked. Exact commands are
appended to [validation](23-validation.txt), with separate follow-up
[source hashes](23-target-source-hashes.json).

Original review/raw measurements/source hashes above remain unchanged and apply
to the initial implementation only. The old cost probe is a historical source
snapshot for that earlier API. This API migration makes no new performance claim
and does not repeat the earlier Python matrix. No commit or push.
