# 07 — Release closed verification runtimes

Created: 2026-11-18  
Status: Complete (keep)\
Priority: P2 — recommended; not a release blocker  
Blocked by: None — can start immediately  
Assignment: `/root/v2_item07` (GPT-6.2 Sol, high reasoning)

## Outcome

Allow a verification report to release its ownership reference to a test runtime after that runtime has explicitly completed cleanup. Keep every open runtime strongly owned so closing the report still performs all outstanding cleanup. This item can start independently; follow the [common measurement and completion criteria](README.md).

## Review evidence

`_VerificationRuntime.create_runtime` appends every runtime to `_runtimes`. Exiting an individual runtime does not remove it; only `_VerificationRuntime.close` or `aclose` clears the list. A retained report therefore keeps closed runtime plans and cached application values alive.

On CPython 3.14.4/macOS ARM64, a report creating 20 sequentially closed runtimes, each resolving one 1 MiB singleton, retained **21,031,275 traced bytes and all 20 payloads** after GC. Closing the report reduced retention to **2,415 bytes and zero payloads**. This is a retention reproduction, not an implementation improvement or an RSS claim. The local probe and results are `.benchbro/v2-perf-review/memory_review_probe.py` and `memory_review_results.json`.

## Implementation scope and guardrails

- Add explicit tracking removal after runtime cleanup completes, for synchronous and asynchronous close. A runtime must remain owned while finalizers are still executing or awaiting.
- Keep strong ownership for open runtimes; replacing the tracker wholesale with weak references would lose its cleanup guarantee.
- Preserve reverse-order report cleanup of remaining runtimes and stable traversal if runtime completion removes entries during report close.
- Define completion and removal consistently when cleanup fails. Preserve exception aggregation, propagation, idempotence, reentrant behavior and concurrent-close reporting; never hide a pending cleanup failure by removing an in-progress runtime.
- Preserve findings, captured graphs, selected registrations and the report's closed-state contract. Do not clear runtime caches or sever references needed by independently retained children/providers. Any such references may legitimately keep a closed runtime alive.

## Acceptance checklist

- [x] Individually closed, otherwise unreferenced runtimes and their payloads become collectible while their report remains open.
- [x] Unreferenced open runtimes remain report-owned and are cleaned up exactly once.
- [x] Report close preserves remaining-runtime order and aggregated failures.
- [x] Sync/async failures, cancellation, reentrant and overlapping close attempts preserve cleanup/error behavior.
- [x] External child/provider references and independent-child semantics remain unchanged.
- [x] Captured findings remain readable; current CI's supported-Python checks pass.

## Validation and measurement

Use weak-reference behavioral tests for early collection and retained cleanup responsibility. Repeat the 20-runtime payload experiment while keeping the report alive; compare retention after GC. Separately measure repeated create/close cycles without tracing to detect tracking overhead. Test an awaiting finalizer to prove ownership persists until completion, and avoid tests that merely assert tracker representation.

## Implementation and decision

Keep the change. The report holds runtimes in creation order. Each runtime
installs an ownership-release callback before resource finalizers, so reverse
cleanup order places release last even when earlier finalizers fail or are
cancelled. The callback weakly references the report's ownership state. Report
cleanup snapshots keys in reverse order and looks up each still-owned runtime.
The tracker frees its backing capacity when its final runtime finishes cleanup.

The fresh baseline was `0763ed4`, including accepted items 01–03 and 05 and the
pre-existing edits to `.github/workflows/ci.yml`, `clean_ioc/_legacy.py` and
`pyproject.toml`. Baseline and candidate ran on the same macOS ARM64 machine with
CPython 3.14.4, BenchBro 1.0.0, typetoolbox 0.4.0 and the same installed dependencies.

| Workload | Baseline | Final candidate |
| --- | ---: | ---: |
| Twenty individually closed runtimes while the report stays open, after GC | 21,027,444 B retained, 20 live payloads | 1,824 B retained, 0 live payloads |
| Peak traced Python allocations during those runtime cycles | 21,067,124 B | 21,067,636 B |
| Same payload workload after report close and GC | 1,888 B retained | 1,856 B retained |
| Burst of 2,000 simultaneously open empty runtimes, after individual closes and GC | 2,928,160 B retained | 32 B retained |
| Peak traced Python allocations during the empty burst | 5,307,824 B | 5,439,334 B |
| Verify, create and close 200 empty test runtimes, then close the report | 4.060 ms | 4.227 ms |
| Ordinary build, create and close 200 empty child scopes, then close the container | 0.584 ms | 0.571 ms |

Memory medians are from five payload trials and three empty-burst trials per
source. Tracing starts after verification and covers runtime projection and
cleanup, plus singleton activation for the 1 MiB payload case. The nearly
identical payload peak reflects cyclic runtime objects awaiting GC in this short
run. The empty burst incurred 2.5% higher peak from the added tracking. These
measurements cover Python allocations. The payload and timing cases are
reproducible with [`benchmarks/bench_verification_runtimes.py`](../../benchmarks/bench_verification_runtimes.py).

Timing medians summarize six alternating baseline/candidate pairs of independent
BenchBro runs, each with 10 warmups, 24 repeat samples of 25 invocations, normal GC
and tracing disabled. The empty verification cycle cost rose in every pair by
1.1–5.1%, with a +3.9% median paired change, or about 0.83 µs per runtime from the
run medians. The build/scope control had overlapping medians and noisy runs on
both sides. That control includes registration and build and does no resolution.
Raw measurements, source selection and the burst probe are in `.benchbro/v2-perf-07/`.

## Final validation and review

Regression coverage uses actual resource factories and weak references for
observed and unobserved runtimes, open-runtime ownership, failed cleanup,
independent child/provider lifetimes and overlapping async close. It verifies
reverse finalization order and profiler counts. The overlapping-close test
observes an awaiting cleanup across duplicate close attempts and confirms that
cancellation reaches the original closer. The six early-release regressions
failed on the unchanged baseline.

Local `make ci` passed on macOS ARM64. CPython 3.11.13 had 2,669 passes and eight
skips, CPython 3.12.11 had 2,674 passes and three skips, and CPython 3.13.5,
3.14.8 and 3.15.2 each had 2,677 passes. The 103 focused tests, strict
documentation build and workflow lint passed. FastAPI 0.121.0 and 0.165.0 each
passed all 16 integration tests on CPython 3.12.11.

Independent review by `/root/v2_item07/review` found stale capacity in the first
tracker and a GC reentrancy risk in the first locking refinement. The final
tracker frees its capacity when empty and snapshots outside the mutation lock.
Review probes covered GC reentrancy, concurrent synchronous close and nested
report close, including exception identity. Re-review found no remaining issues.
