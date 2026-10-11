# 18 — Verify both modes and combined compiler-memory gains

Created: 2026-10-10\
Status: Complete — combined qualified KEEP accepted after coordinating review; [result](18-result.md)\
Assignment: `/root/graph_memory_task_18`, high reasoning, sequential workstream\
Recommended reasoning effort: High (`high`)\
Priority: Baseline first; combined acceptance last\
Prerequisites: 10–11 contracts and each candidate selected from 12–17

## Outcome

Establish that the final two-mode API preserves application behaviour and analysis
coverage, and that integrated changes improve the intended memory/time measures.
Do not add individual experiment savings to predict the combined result.

## Baseline and protocol

- Record the exact revision, dirty changes, interpreter, architecture, source
  hashes, fixture and mode/capability settings. Preserve the current consumer
  validation fix and distinguish the working tree from published RC4.
- Start with the rich eight-route fixture and bounded small controls. Add cases
  with legacy rich build rules, narrowed rules, diagnostics-heavy analysis,
  high definition diversity, sparse indexes and caller-retained snapshots.
- Run at least three fresh untraced processes and three separate traced processes
  serially per meaningful comparison, without competing tests/benchmarks. Record
  ranges and all samples; expand only where a real uncertainty needs resolution.
- Separate imports/composition, compiler phases, full validation, freezing,
  retention, cold/steady resolution and optional inspection. Report current/peak
  RSS, traced retained/peak bytes, counts and durations separately.
- Constructor/GC census observers run outside benchmark samples. Distinguish
  total objects created, simultaneously live objects and final retained objects.
  Include pools, adapter/promotion overhead and caller-owned data where relevant.

## Behaviour and consumer coverage

- Run and analysis select the same registration/decorator targets and preserve
  lifetimes, cleanup, lazy providers/maps, filters, slots, warmups and ownership.
- Discovery remains complete without adding public roots. Bark/Cop-shaped command
  and saga bundles retain both build-mode and validation-only rule registrations.
- Mandatory checks reject bad builds in either mode; fresh analysis runs all
  intended validation and exposes complete supported evidence. Run APIs report
  discarded capabilities explicitly and never replay callbacks or recompile.
- Test defaults, migration diagnostics, CLI/matrices, repeated reports, supported
  overlays, failed-builder retry and relevant profiling/instrumentation paths.
- Run appropriate full tests, lint/format/type checks, executable docs, strict
  docs and supported-Python checks. Preserve known experimental-version failures
  accurately rather than weakening assertions to obtain a green result.

## Application and artifact verification

Arrange local Bark/Cop verification against the identified checkout/package when
that integration work is assigned. Distinguish library tests, downstream unit
tests, integration tests and container-memory measurements. Use matching Python,
architecture/image and metric definitions for application comparisons; do not
equate local ARM Docker readings with production x86 Datadog metrics.

Existing artifact round trips are compatibility checks where touched, not an
authorization to implement pre-compilation or deploy/restart production.

## Acceptance and deliverables

- A mode capability/equivalence report, runnable reproduction commands and raw
  evidence with source identity. No constructor activation during compilation.
- Individual and combined measurements against the same baseline. Explain which
  gains concern peak memory, retention or CPU and identify observed regressions.
- Explicit keep/refine/drop decisions for each integrated candidate. Record any
  unresolved default/migration or performance tradeoff before production readiness.
- Updated work-item statuses and user-facing two-mode documentation. Commit,
  push and release are separate actions and are not part of this planning task.

Readiness gate: baseline capture can be scoped immediately; final acceptance
requires the selected implementation set and settled contracts from 10–11.
