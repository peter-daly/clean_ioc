# Item 15 — independent review

Status: complete — **KEEP**. All review findings resolved; no open correctness
findings. CI, supported-Python checks and repeated performance evidence reviewed.
Reviewer: separate Astra high agent, independent of implementation (Astra medium).
Scope: item 15 only, compared with the completed, uncommitted item 14 source pinned
at `.benchbro/chained-preferences.0uxthurn/base`, not Git HEAD. No production edits,
commits, pushes or version changes were made by this reviewer.

## Final assessment

**KEEP.** Ordered soft fallback adds observable value:
it chooses the preferred available registration across order permutations, retains
fallbacks when a rule misses, and allows different consumers to choose different
registrations without excluding valid fallbacks. It does not improve a decision
already settled by a hard filter or numeric maximum. Registration-side chains add
coordination cost: an application fallback registered later can lose to a library's
soft rule, so consumer preferences and explicit precedence need clear documentation.

Hard selection is simpler when exactly one implementation is valid. Numeric
precedence remains simpler for one global priority, and controlled registration
order remains adequate where the composition root owns every registration. The
feature earns its API cost when reusable ordered preferences must keep fallback
candidates, especially when several independent packages contribute alternatives.
No weights, specificity inference, selector fingerprint changes or runtime ranking
were introduced in the reviewed design.

## Findings and repairs

1. **Fixed, independently verified — Python 3.11 async partial validation.**
   `_validate_stage` checked either the callable or its `__call__` depending on
   `inspect.isroutine`. On Python 3.11, a partial wrapping an async/generator function
   is not a routine, so the recognized coroutine/generator flags were lost.
   Validation now checks both surfaces. Nine forms (coroutine, generator and async
   generator functions, their partials, and corresponding callable objects) were
   independently rejected on the available Python 3.11 environment.
2. **Fixed, independently verified — failed preference callbacks fabricated winners.**
   The initial failure branch put original `selected` decisions into the rejected
   tuple. Failed and unexamined candidates appeared as `attempt-selected` in the
   failure census. Reproduction with two eligible registrations and a throwing
   first stage now captures no winner and distinct failed/not-examined decisions.
   Error payload text remains redacted. A separate later-stage failure reproduction
   also preserves earlier eliminated C, already-evaluated B (`selection-incomplete`),
   and failed A, without claiming a selected candidate for that occurrence.
3. **Fixed, independently verified — unreachable tails.**
   The initial implementation traversed every original candidate at every configured
   stage after a unique winner, allocating skipped evidence proportional to the
   unreachable suffix. It now records a compact `through_stage` range and exits.
   Independent chains of lengths 1 and 64 execute exactly two first-stage callbacks
   with two candidates. Repeated parent-owned builds with 1, 8 and 64 stages
   show no cost growth with the unreachable suffix (details below).
4. **Minor diagnostic precision raised — eliminated candidates in compact ranges.**
   When the remaining registration chains are exhausted but a tie survives,
   eliminated original candidates should remain `not-reached`; they should not be
   relabelled `missing-rule`/`masked-context`. This was repaired using occurrence IDs
   without candidate equality or quadratic membership work.

5. **Fixed — no-chain diagnostic compatibility.** The initial final-tie refactor
   changed item 14 reason text even when no chains were configured. Original reason
   text has been restored for the no-chain path.
6. **Fixed, independently verified — absent chain mislabelled as masked context.** A fast-path
   optimization avoids capturing a source view for registrations without a chain.
   The normal stage loop must check absent/missing rule before using a missing view
   as evidence of masked context. The check order is repaired and a dedicated regression
   test passes on Python 3.11. Selection was unaffected; this was evidence precision.

## Independent before/after probes

The reviewer wrote a separate executable real-compiler probe at
`/tmp/review15_probes.py`. The same eligible registrations and metadata were run
against the pinned item 14 tree and the candidate; only preference declarations
were added in after mode. Raw outputs are separate files
`/tmp/review15_before.json` and `/tmp/review15_after.json`; neither overwrote the
other. The implementation's persistent before/after artifacts remain authoritative
archival evidence; these independent outputs cross-check the behavior.

Registration orders below are earliest to latest; ordinary fallback selects the
last registration. Candidate callback order was checked against the existing
reverse registration order, retaining every match at each stage.

| Probe | Before, completed item 14 | After, item 15 | Independent observation |
| --- | --- | --- | --- |
| P1 primary, then EU | A wins 2/6 | A wins 6/6 | 3 first-stage + 2 second-stage calls per build |
| P2 no primary match | EU wins 1/2 | EU wins 2/2 | 2 + 2 calls; no missing-component failure |
| P3 primary dominates EU/name | A wins 1/2 | A wins 2/2 | 2 first-stage calls; later stages skipped |
| P4 parent-specific registration chains | Both parents receive same LIFO registration | Europe/America winners in all 6 orders | No parent inherits another occurrence's decision |
| P5 sync and async provider | Ambiguous at equal explicit precedence | Unique A target | 2 callbacks per successful build; still errors if final chain ties |
| P6 `[false,true]` vs `[false]` | LIFO | First chain wins both orders | Exactly 3 callbacks |
| P6 `[true]` vs `[false,true,true]` | LIFO | First chain wins both orders | Exactly 2 callbacks; no tail work |
| P6 `[false]` vs absent | LIFO | LIFO | Exactly 1 callback; missing rule neutral |
| P6 exhausted false chains | LIFO | LIFO | Exactly 3 callbacks; warning retained |

Detailed P1 and P4 permutation record:

| Registration order | P1 before | P1 after | P4 before (Europe, America) | P4 after |
| --- | --- | --- | --- | --- |
| A, B, C | C | A | C, C | A, B |
| A, C, B | B | A | B, B | A, B |
| B, A, C | C | A | C, C | A, B |
| B, C, A | A | A | A, A | A, B |
| C, A, B | B | A | B, B | A, B |
| C, B, A | A | A | A, A | A, B |

The P5 final-tie failure recorded four callback calls across the existing primary
and diagnostic compilation attempts, not four calls in one selection occurrence.
That distinction is explicitly allowed by the work-item contract.

Controls independently passed:

- Hard filter excludes preferred candidates: C wins all six orders; zero preference
  calls once the filter leaves one candidate.
- Consumer chooses B before A's registration preference. A's unique higher numeric
  precedence instead wins with zero preference calls.
- Unnamed default eligibility continues excluding named candidates.
- Collection order remains C, B, A; consumer and registration preference callbacks
  both remain uncalled for membership.
- One eligible candidate skips all callbacks; all-true and all-false chains retain
  ordinary LIFO and warning semantics.
- Repeated graph/census rendering and runtime resolution do not replay callbacks.

## Independent context and lifecycle checks

A second reviewer script, `/tmp/review15_context.py`, passed these actual compiler
checks, separately from the implementer's test suite:

- Exported registrations with hidden parent context do not run even a raising
  registration preference. Boundary export ambiguity retains exact cardinality.
- A provider target sees its synthetic provider as immediate parent. Matching its
  worker requires explicit nested `cf.parent`; the direct-parent rule remains a tie.
- Parentless roots, preview APIs, provider-map membership and duplicate-key checks
  execute zero configured registration preference callbacks. Duplicate keys still
  fail with the original provider-map error.
- Parent singleton plans remain anchored; new overlay occurrences can select the
  overlay registration while inherited singleton dependencies retain the old choice.
- Profiling records exactly two actual callbacks in an unresolved two-candidate
  stage. Profile reports, manifest/census output and activation add no callbacks.
- All-true preferences that preserve the final dependency edge also preserve the
  static graph fingerprint.

Additional reviewer script `/tmp/review15_alias_failure.py` verified source-side
registration service/name/tags/internal-parent context, consumer-side exported alias
service/name/tags, type-alias preference transport, and precise later-stage failure
evidence. The checked-in feature and item 14 suites passed together on Python 3.11:
**110 passed** (63 preference cases, 47 parent-precedence cases). After the final evidence-only fix, four targeted tests passed (60 deselected),
including the new missing-rule regression.

The documentation review confirms the default unnamed filter, conflict precedence,
collection bypass, provider synthetic parent, `.then()` immutability, library/app
coordination, patch clear/unchanged semantics, failure/retry rules and alternatives
are explained in `docs/advanced/filtering.md`.

## Final verification

Source, focused tests and context/metadata review are complete. Parent confirmed
`make ci` passed with **1,072 tests**, including all **64 new preference tests**,
plus lint, formatting, types and documentation checks (archived at
`.benchbro/chained-preferences.0uxthurn/ci-314.log`).
Earlier complete suites passed on Python 3.11 (**1,052 passed, 8 skipped**), 3.12
(**1,057 passed, 3 skipped**) and 3.13 (**1,060 passed**). After the final small
changes, the affected six-module suite passed **282 tests on each** of 3.11, 3.12
and 3.13; this is an affected-suite recheck, not a claim of a second full run.
The final source is frozen in `.benchbro/chained-preferences.0uxthurn/current`
with hashes in `current-metadata.json`. The reviewer independently rehashed both
archived before-probe outputs, all 37 baseline source files and all 40 final source/
benchmark files against the stored metadata; every hash matched.

The reviewer read the BenchBro skill and its reliability and advanced-boundary
guidance. No benchmark was rerun by the reviewer during parent timing windows.
The benchmark source and final public/use-case documentation were reviewed.

## Performance assessment

The reviewer independently read all four primary raw JSON reports and all four
three-case tail reports. The same Python 3.14.4 interpreter, machine, dependencies
and workload source were used for baseline and candidate. The baseline is completed
item 14, not Git HEAD. Chain construction is deliberately outside timing; registration,
compilation and container close are inside build timing. Runtime fixtures are built
and warmed outside timing. Provider control builds are successful on both versions.

The table uses the arithmetic mean of the two run medians, not pooled samples.
Representative build cases have 16 candidates and eight parent occurrences:

| Workload | Completed item 14 | Item 15 | Change |
| --- | --- | --- | --- |
| No chain | 16.59 ms | 17.14 ms | +3.27% |
| Consumer unique at first stage of eight | 16.75 ms | 17.98 ms | +7.35% |
| Consumer unique at final stage of eight | 16.40 ms | 19.05 ms | +16.17% |
| Registration unique at final stage of eight | 16.50 ms | 19.89 ms | +20.59% |
| Unique-eligible provider control | 15.51 ms | 15.72 ms | +1.38% |
| Collection membership bypass | 21.58 ms | 21.55 ms | −0.13% |

Across all four no-chain build sizes the changes are −0.05% to +3.27%. Across
runtime cases they are −2.38% to +1.88%. Unchanged baseline runs themselves drifted
−5.44% to +5.02%, and many raw runs have outlier/noise flags, so these control-path
changes do not establish a repeatable regression or a speedup. The larger enabled
build costs are real enough to disclose; this feature is not a compilation-speed
optimization and still validates losing candidates.

The early-winner tail experiment independently confirms the repair: candidate
medians averaged **18.05 ms** for one stage, **18.53 ms** for eight stages and
**17.72 ms** for 64 stages. Callback counts remain exactly one stage per survivor.
The data support bounded skipped-tail work; they do not imply zero chain overhead.

**The measured cost is acceptable for KEEP**: the feature demonstrably adds ordered
fallback and parent-dependent choice at build time, leaves activation free of
preference work, and has no control-path regression established beyond the measured
desktop variation. Long unresolved chains are an explicit compilation cost; no
universal performance budget or production latency guarantee is inferred. Full raw
quality fields, limits and compatibility results are retained in the
[performance report](15-chained-preferences-performance.md).

No remaining implementation, diagnostic, verification or benefit finding blocks
acceptance of item 15. Commit, push, release and version changes remain outside this
assignment.
