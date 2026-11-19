# Item 23 — independent review

Status: complete — **APPROVE / KEEP**. All correctness findings raised during
review were repaired and independently rechecked. No open finding blocks the
unified container/scoped slot contract.

Scope: the uncommitted item 23 implementation in `clean_ioc/container.py`,
`clean_ioc/components.py`, `clean_ioc/graph_analysis.py`, its focused tests,
slot/scope/lifespan/warmup documentation, executable-doc validation, changelog
and navigation. The reviewer made no production edits or commits; this file is
the only reviewer-authored repository change.

## Findings and repairs

1. **Fixed — later shared-binding views escaped implicit/explicit conflict
   validation.** Declaration validation originally retained one representative
   per explicit binding. An explicit binding with views named `first` and
   `second`, followed by an implicit `second` declaration, therefore built and
   failed only when `provide(..., name="second")` found two bindings. Validation
   now checks every view and fails the build with
   `slot-implicit-binding-conflict`, source-linked evidence and a path.

2. **Fixed — root registration precedence was not applied to boundary imports.**
   `Use.root(T)` combined registration and slot matches, producing
   `boundary-use-ambiguous`, or rejecting a conditional slot, even when a normal
   or fallback registration already won. Boundary preparation now considers
   slots only when no registration matches. Build and verification coverage
   includes unconditional and conditional slot declarations.

3. **Fixed — private architecture boundaries leaked conservative managed roots
   into readiness.** With automatic provider roots disabled, adding an unrelated
   private boundary could make an otherwise unused conditional container slot
   required through internal `AsyncManagedProvider` adapters. Required-input
   traversal now begins with public roots, declared provider roots and warmups;
   it reaches internal managed adapters only from a reachable managed
   `ResolutionContext`. Tests cover both the private-boundary exclusion and a
   reachable dynamic managed target that must require its slot.

4. **Fixed — compatibility shorthand was not idempotent across inherited
   overlays.** Repeating `declare_scope_slot(T)` in a `ScopeBuilder` over an
   inherited identical shorthand declaration produced `duplicate-slot`. The
   shorthand now recognizes inherited implicit scoped declarations while still
   rejecting a container/scoped lifetime conflict and repeated unified implicit
   declarations.

5. **Fixed — observed provider wrappers hid slot identity.** Instrumented
   provider plans were not unwrapped far enough for registration precedence and
   shared-binding deduplication. Root selection now unwraps observed call-site
   and provider wrappers. Build and verification runtimes cover registration
   precedence and one-member shared binding collections under instrumentation.

6. **Fixed — declaration and root ambiguity diagnostics lacked actionable
   origins.** Duplicate/incompatible/conflicting declarations and ambiguous
   direct/deferred roots now include every relevant contract, binding, source
   location, path and structured evidence. This satisfies the repository rule
   that invalid composition fail with an actionable dependency path.

The review also noted two non-blocking maintenance risks. Slot identities remain
available both as rich declarations and a derived legacy `(type, name)` view,
although the separate mutable origin map was removed during review. Required
input discovery has its own executable traversal because it tracks managed
context reachability; new executable carrier types must continue to be assessed
for that traversal as well as runtime graph retention/reduction.

## Independent validation

- `tests/test_unified_slots.py`: **77 passed** after all repairs.
- Slot, container, reduced-runtime, warmup, alias and activation-cache focused
  suite: **331 passed**.
- Separate direct probes reproduced each of findings 1–4 before repair and pass
  against the final source.
- Ruff and `ty check clean_ioc`: passed.
- Executable documentation validation: passed.
- `mkdocs build --strict`: passed, with only the existing tool deprecation and
  project evidence-page notices.
- `git diff --check`: passed.

The implementation owner reported the earlier Python 3.14 full CI at 2,586
tests with the existing FastAPI warning, plus complete Python 3.11–3.14 runs
before the review-stage repairs. I did not repeat those full suites or the
performance measurements. The final repairs are covered by the focused checks
above; the implementation owner will rerun the complete supported-Python matrix.
Artifact export/loading and downstream application benchmarks remain outside
this item's acceptance gate.

Final delta confirmation: after the main review, `_find_provision()` was changed
to compute the frozen slot key once per lookup and reuse it for local, container
and ancestor provision checks. This is behavior-preserving and introduces no
contract or ownership change. The unified-slot and alias suites pass together
with **92 tests**; focused Ruff and type checks also pass. The verdict is
unchanged.

## Verdict

**APPROVE / KEEP.** The final implementation preserves registration cardinality
and precedence, freezes contextual binding choice without runtime predicate
replay, enforces container/scoped ownership and sealing, derives readiness from
the intended frozen surfaces, preserves caller ownership, and covers full and
reduced runtimes, overlays, supported boundaries, providers/maps, decorators,
pre-configuration and warmup behavior. No remaining review finding warrants a
production change.
