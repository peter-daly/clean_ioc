# 15 — Measured chained-preference use cases

Status: Complete — implemented, measured and independently reviewed (KEEP)\
Date: 2026-09-27\
Implementation: Astra Medium; independent review: Astra High

## Reproducible baseline and evidence

The baseline is the completed, uncommitted item 14 tree at
`.benchbro/chained-preferences.0uxthurn/base`, pinned by
`.benchbro/chained-preferences.0uxthurn/baseline-metadata.json`.
HEAD `63cbea4` alone is not the baseline. Before runs
imported that tree with `PYTHONPATH`; after runs imported the working implementation.
The same registrations, order, metadata, filters and numeric precedence were used;
after mode adds only consumer and registration preference declarations.

The real compiler produced 55 primary cases and eight context/control cases per
version. Probe outputs use exclusive file creation, so rerunning a command cannot
overwrite baseline evidence. [Baseline evidence hashes](probes/15_baseline_metadata.json)
record the immutable before files. These are behavioral probes, not simulated
ranking or numerical scoring:

- [Primary probe](probes/15_chained_preferences.py), [before](probes/15_before.json),
  [final after](probes/15_after_final.json).
- [Context probe](probes/15_context_probes.py), [before](probes/15_context_before.json),
  [final after](probes/15_context_after_final.json).

Each result retains actual registration order, winners or error codes, warnings,
collection order and observed preference callbacks. The primary probe includes
root results. The context probe retains synthetic-provider context, map keys,
boundary failures, anchored identity and runtime callback counts. Earlier after
recordings remain as development evidence; final-after files are authoritative.
Callback totals for failures can include existing diagnostic retries; the profiler
and regression tests distinguish primary and retry attempts.

## Results

| Case | Completed item 14 before | Chained preferences after |
| --- | --- | --- |
| P1: primary, then EU | A wins 2/6 orders | A wins 6/6; three callbacks at stage 0, two at stage 1 |
| P2: no primary matches | EU A wins 1/2 | A wins 2/2; all-false first stage preserves fallback |
| P3: primary versus two later matches | A wins 1/2 | A wins 2/2; later stages cannot outweigh primary |
| P4: batch/EU and batch/US parents | Both consumers get the same LIFO policy in each order | Europe gets A and America gets B in all 6/6 orders |
| P5: injected sync/async provider | Ambiguous in both orders and both modes | A is the unique frozen target in all four cases; final all-true ties still error |
| P6: different chain lengths | LIFO | `[false,true]` beats `[false]`; `[true]` beats `[false,true,true]`; `[false]` versus absent stays LIFO |
| G1: hard filter | B only | B only; excluded A never returns and no preference callback runs |
| G2: consumer versus registration | LIFO | Consumer B wins both orders; higher numeric A wins before callbacks |
| G3: default unnamed filter | A only | A only; named B remains excluded |
| G4: collection membership | Both members, reverse registration order | Identical membership/order, zero preference callbacks |
| G4: maps and cardinality | B/A map; duplicate-key and Expose ambiguity errors | Same keys/order/errors, zero preference callbacks |
| G5: boundary context | Local B | Local B; hidden registration rule skipped without invoking it |
| G5: alias public view | Local unnamed B | Consumer sees public alias/name and chooses A |
| G5: provider ancestry | Both requests ambiguous | Immediate worker-parent rule still ambiguous; explicit nested-parent rule uniquely selects A |
| G5: overlay anchoring | Original singleton uses B, new injection B | Original singleton uses A and remains the same object; new injection B; zero runtime preference callbacks |
| C1: single/all-true/all-false | Single or LIFO | Identical choices; single candidate invokes no preference callbacks |
| C2: disjoint filter/unique numeric maximum | Already unique | Unchanged, zero preference callbacks; no claimed selection benefit |
| R1: shared prefix extension | LIFO | Original and extended chains choose A in both orders; callback counts unchanged after unique prefix |
| R2: library soft rule | Later registration wins | A's true registration rule beats later B; explicit application coordination is required |

P6 missing-stage ties and all-true/all-false controls retain ordinary ambiguity
warnings. Preferences never turn a nonempty eligible set into an empty set.
The tests additionally verify every decisive stage position, composed predicates,
ID predicates, generic binding inspection, exact/pattern/open-generic tiers,
discovery and fallback patches, aliases, repair after failed build, ownership,
collection/map member dependencies, declared factory requests, slots and scope
lifecycles.

## Benefit and limits

The useful difference is ordered desirability with valid fallback. Numeric
precedence expresses a single fixed registration priority; it cannot by itself
give EU and US consumers different winners when every policy is valid for both.
Hard selection can enforce the desired answer but loses fallback unless application
code explicitly reconstructs it. Mutually exclusive `when` rules are appropriate
when the other implementations are invalid; using them merely to express a
preference unnecessarily removes alternatives. Controlled registration order is
simpler where one override policy suffices, but cannot express the two regional
choices simultaneously.

Consumer chains also make the dependency's ordering explicit and reusable without
inventing weights or predicate-specificity rules. Their value is not in changing
already-unique choices, ranking collections, or optimizing graph compilation:
losing candidate graphs still compile and validate.

The added cost is a second coordination surface for library authors. A nonempty
registration chain can defeat a later zero-precedence application registration.
Public docs explain deliberate application overrides through a consumer chain,
hard filter or stronger numeric precedence. Stage callbacks must be pure and
synchronous; only reached stages run. Compact captured skip ranges keep a uniquely
decided prefix independent of its unreachable tail's length. This needs to be
weighed against measured compile overhead in the separate
[performance report](15-chained-preferences-performance.md).

Implementation recommendation: **KEEP**, for P1/P2/P4/P5's demonstrated fallback
and context-dependent choices, with the above coordination contract documented.
The separate [independent review](15-chained-component-preferences-review.md)
also concludes **KEEP** after checking correctness and the measured cost.

## Verification

`make ci` passed on Python 3.14.4: **1072 tests passed**, including **64 new
preference tests** and all 47 item 14 regression tests. Ruff lint/format, static
typing, executable documentation examples and BenchBro discovery also passed.
The only warning was the existing Starlette/httpx deprecation warning. Full CI
output is retained at `.benchbro/chained-preferences.0uxthurn/ci-314.log`.
The [performance report](15-chained-preferences-performance.md) records the
supported-Python matrix and 27 repeated baseline/candidate benchmark cases,
including final affected-module passes on Python 3.11–3.13. Long chains add
measurable compilation cost; runtime differences remain within observed variation.

No commit, push, release or version change was made. Item 13's retired ordinary
filter scoring remains retired.
