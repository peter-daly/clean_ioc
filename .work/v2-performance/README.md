# V2 performance and memory implementation work

Created: 2026-11-18  
Status: Items 01–03, 05 and 07 complete (keep); 04 and 06 declined and stashed.\
Review baseline: Working tree based on `3246679`, Clean IoC `2.0.0rc6`  
Assignment: Each implementation item — GPT-6.2 Sol, high reasoning

## Sequential execution instruction

The maintainer authorized items 03–07 in numerical order, each assigned to a
Sol agent at high reasoning. Finish measurement, validation and independent
review of one item before starting the next. Commit each accepted improvement
locally. If a candidate does not demonstrate a worthwhile improvement, stash
only that item's changes and record the stash reference, immutable stash commit
ID and rejection reason here before proceeding. Preserve unrelated working-tree
changes. Do not push or release.

Item 01 was assigned on 2026-11-18 to `/root/v2_profiler_histograms`
(`gpt-6.2-sol`, high reasoning) for implementation and validation. It passed
the local Python 3.11–3.15 checks. Independent review by
`/root/v2_profiler_histograms/review` found no actionable issues.

Item 02 was implemented and validated by `/root/v2_scope_owner_maps`
(`gpt-6.2-sol`, high reasoning), with the accepted item 01 change in its
baseline. Local Python 3.11–3.15 checks passed. Independent review by
`/root/v2_scope_owner_maps/review` found no actionable issues.

Item 03 was implemented and validated by `/root/v2_item03` (`gpt-6.2-sol`, high
reasoning), with items 01–02 in its baseline. Local Python 3.11–3.15 checks
passed. Independent review by `/root/v2_item03/review` found no actionable issues.

This work list captures all seven findings from the pre-v2 performance review,
including the verification-runtime retention finding. Creating these items does
not start implementation or mark any prototype as accepted production code.
Existing compatibility and CI edits were present during the review and must be
preserved.

## Work items

| ID | Work item | Recommended priority | Review evidence | Blocked by |
| --- | --- | --- | --- | --- |
| 01 | [Allocate profiling histograms on demand](01-lazy-profiling-histograms.md) | P1 | Counts-only profiling, 100 services: retained Python allocations 225.21 → 24.89 MB in final implementation | None |
| 02 | [Share owner maps between ordinary scopes](02-share-scope-owner-maps.md) | P1 | 1,000 empty scopes below the root: retained Python allocations 904,832 → 720,832 bytes in final implementation | None |
| 03 | [Remove registry rescans during registration](03-remove-registration-rescans.md) | P1 | 5,000 repeated declarations: 571.8 → 323.5 ms in final implementation | None |
| 04 | [Reuse subplans when generated decorators cannot apply](04-reuse-subplans-with-unmatched-decorators.md) | P2 | Declined/stashed: speed gain changes opaque wrapper behavior | None |
| 05 | [Fast-path cached generic roots and provider targets](05-fast-path-cached-generics-and-providers.md) | P2 | Final warm generic roots 17.5–25.5% faster and ordinary provider calls 39–47% faster | None |
| 06 | [Fast-path fully cached async collections](06-fast-path-cached-async-collections.md) | P2 | Declined/stashed: cancellation and closure behavior changed | None |
| 07 | [Release closed verification runtimes from their report](07-release-closed-verification-runtimes.md) | P2 | Twenty closed runtimes, report open: 21.03 MB → 1.82 KB of retained Python allocations | None |

Priorities are recommendations, not release blockers. Start with 01–03; 02 and
03 are the smallest changes. Items 04 and 06 need particular care around compiler
callbacks and asynchronous execution. No item requires another item to land.
Items 02, 05, 06 and 07 touch related ownership/resolution behavior, so coordinate
edits and rerun their shared behavior tests after integration. That overlap is
not a dependency or a reason to introduce a shared refactoring ticket.

## Evidence and measurement rules

The review used CPython 3.14.4 on macOS ARM64. Timing results are exploratory
same-machine comparisons of the working tree and temporary process-local
prototypes. Memory results describe traced Python allocations, not process RSS.
The individual items retain workload definitions, measurements and limitations;
none depends on the survival of the temporary review probes.

- Capture a fresh unchanged baseline before each implementation. Record the
  source revision and any working-tree changes, interpreter, dependencies,
  platform, fixture and measurement boundaries.
- Use the project's benchmark workflow for repeatable before/after evidence.
  Alternate baseline and candidate runs, inspect variation and repeat unchanged
  code when a small difference may be noise. Do not measure timing under tracing.
- Measure retained memory after GC and peak allocation separately. State whether
  declarations, compilation, activation, scope creation and cleanup are included.
- Include a representative improvement case and controls that do not benefit.
  Existing percentages are evidence for investigation, not hard CI thresholds or
  promises of application throughput. Report regressions and tradeoffs explicitly.
- Preserve the Python implementation and current public API. These items do not
  reopen native backends, pre-compilation or cross-build caching.

## Completion criteria

- [ ] Each retained change satisfies its behavioral acceptance criteria, with
  focused regression coverage for real ownership, selection or observation rules.
- [ ] Applicable repository checks and the supported-Python CI matrix pass; use
  the current repository configuration rather than this review's interpreter as
  the supported-version list.
- [ ] Final measurements demonstrate a worthwhile benefit without unexplained
  regressions in controls. A promising prototype is not sufficient acceptance.
- [ ] An independent implementation review is complete and findings are resolved.
  Implementation and reviewer assignments remain unassigned until work starts.
- [ ] Each item records its final implementation, validation, measurements and
  keep/refine/decline decision; update this index accordingly. Document any
  user-visible change and update the changelog when applicable.

## Sequential results

- Item 03: accepted and committed locally as `b27f196` (`Avoid full registry scans during registration`).
- Item 04: declined because subtree reuse changes opaque wrapper behavior; candidate stored as `stash@{0}` at creation, immutable stash commit `b9c67d31b685930ea47e9d15a7477639527e4377`. See the item for review counterexamples and measurements.
- Item 05: accepted after Python 3.11–3.15 validation and independent review by `/root/v2_item05/review`. See the item for the cold activation tradeoffs.

- Item 05: accepted and committed locally as `9fdc9b1` (`Fast-path cached generic roots and provider calls`).
- Item 06: declined due to cancellation, closure-ordering and deep inherited-scope differences; stash `9b21605413ffad4561481efaec30639b16dc2fe8` (`stash@{0}` at creation). Item 04 is now `stash@{1}`; its immutable ID above remains authoritative.
- Item 07: accepted after Python 3.11–3.15 validation and independent review by `/root/v2_item07/review`. The item records the retention improvement and the measured empty-runtime overhead.

- Item 07: accepted after independent review and supported-Python checks. Closed-runtime retention fell from 21.03 MB to 1.82 KB with the report open; verification runtime lifecycle overhead is about 0.83 µs per runtime. Committed with its final result record.
