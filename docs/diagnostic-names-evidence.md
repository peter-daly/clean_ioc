# Diagnostic name reuse evidence — 7 October 2026

The compiler now owns an identity cache for rendered diagnostic names and a string pool for equal labels. Recursive
generic rendering shares that cache. Compiler paths, partial failure labels, annotation explanations, generic bindings,
and template labels use it. Frozen records retain strings; caches retain source references only until their compiler is
released. Public `qualified_name` remains live and preserves its existing spelling, including alias-specific grammar.
Metadata names are intentional first-use snapshots per compiler; new builds, retries, and overlays use fresh caches.
There is no process-wide cache, monkeypatch, activation reuse, or change to selection callback execution.

These measurements isolate this change from the preceding occurrence-path cache change. The baseline is a source
snapshot of `3d576f10427d506b414889af21ad95291c39cccf` plus that preceding uncommitted change. The candidate adds
only diagnostic name reuse. Both use Python 3.14.4 on macOS 26.7.1 arm64. Exact measured source hashes and raw
samples are in `benchmarks/diagnostic_names_results.json`; earlier compiler evidence was preserved.

## Synthetic generic routes

`benchmarks/diagnostic_names_evidence.py --routes 512` compiles 512 roots sharing a three-level closed generic
infrastructure chain, with automatic provider roots. Each measurement starts a fresh process. One uninstrumented
sample is retained for each revision; these numbers are illustrative, not confidence intervals.

| Measurement | Before | After |
| --- | ---: | ---: |
| Build time, uninstrumented | 1.228 s | 0.686 s |
| Process peak RSS, uninstrumented | 113.48 MiB | 80.58 MiB |
| Physical component records | 16,384 | 16,384 |
| Provider view contexts | 8,192 | 8,192 |
| Retained diagnostic string objects | 51,223 | 27,165 |
| Distinct diagnostic strings | 17,951 | 17,951 |
| Actual retained diagnostic string storage | 5,349,622 bytes | 3,023,967 bytes |

The storage inventory follows frozen occurrence, parameter, and generic explanations and counts each string identity
once using `sys.getsizeof`. It excludes other graph storage and allocator overhead; unchanged distinct string contents
and graph counts rule out a reduction achieved by dropping evidence or changing budget units.

A separate `--heap` run starts `tracemalloc` immediately before compilation. Traced retained allocations fall from
31,576,580 to 29,277,383 bytes; traced peak allocations fall from 44,293,005 to 40,194,885 bytes. Its instrumented
elapsed/RSS samples remain separate from the uninstrumented comparison.

To compare revisions, run the same saved probe script with the desired checkout on `PYTHONPATH` and the same
interpreter/dependencies. The probe performs ordinary builds; it does not replace compiler methods.

## Isolated Cop worker development probes

Disposable application copies from the earlier Cop composition experiment were reused with the existing isolated
Python environment. Config construction precedes timing, and settings values are never printed. Each pair changes
only the imported Clean IoC source, with no cache monkeypatch or compilation profiler. One fresh-process sample
per configuration was measured.

| Composition | Before time | After time | Before peak RSS | After peak RSS |
| --- | ---: | ---: | ---: | ---: |
| Unchanged worker composition | 22.655 s | 13.176 s | 1,487.73 MiB | 1,455.77 MiB |
| Earlier experimental narrowed composition | 10.123 s | 5.812 s | 609.97 MiB | 450.11 MiB |

The unchanged composition retains exactly 151,633 physical records and 4,764 view contexts in both runs; the
experimental narrowed composition retains 79,642 records and 3,132 contexts in both runs. The original worker's
RSS improvement is modest despite substantial time savings. The narrowed composition already changes application
root exposure and remains experimental; its figures do not establish acceptance of that composition or this library.

This is macOS source-selected development evidence. It is not released-wheel downstream testing, Linux readiness
measurement, or proof of the unchanged 512 MiB / 100m deployment gate. No shared Bark/Cop checkout, lockfile,
package version, deployment limit, or historical benchmark sample was changed.

## Verification

New tests cover exact generic, union, Literal, NewType, and alias spelling; recursive child reuse; equal string storage;
unsupported values and hostile string metadata without hashing, equality, or representation callbacks; failed-build
retry metadata refresh; live public names; reentrant builds; overlay isolation; cache/source garbage collection,
including budget/profile builds; retained explanation string identity; and runtime provider resolution.

`make ci` passed: Ruff lint/format, ty, 1,786 tests, documentation example validation, and BenchBro discovery.
The existing GC-disabled failed-budget compiler-retention test remains intact and passes. Failure reporting
pre-renders labels before its recursive path helper to avoid creating a compiler-retaining closure; measured
successful build paths are unchanged by that final repair.
