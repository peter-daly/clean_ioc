# Work item 14 — independent review

Reviewer: separate Astra agent, high reasoning. Base: `63cbea4`.

Status: complete; both findings resolved. No remaining actionable findings.
The final compatibility/performance report has also been independently reviewed.

## Findings

1. **P2 — census must describe the actual selection rule. Resolved.**
   The new eligible-but-not-selected classification originally inherited
   `first-eligible-wins` unconditionally. This was false when an older preferred
   registration beat a newer fallback, and when a provider had no unique winner.
   The same problem affects tied maxima if the first eligible candidate has a
   lower value. The fix excludes all three parent-precedence loss codes from
   this legacy annotation. Added assertions cover both lower values and ties.

2. **P2 — unlimited integer declarations must survive diagnostic rendering.
   Resolved.** The public contract has no maximum, but
   formatting a maximum such as `10**5000` with a decimal f-string exceeds the
   default integer-to-string limit on supported Python versions. The same issue
   applies to JSON serialization of the captured integer. Selection must not
   fail merely because an otherwise valid value cannot be printed in decimal.
   The fix removes decimal interpolation from reason prose, retains the exact
   integer in `CandidateDecision`, and serializes values above 2000 binary
   digits as an exact `{"integer_hex": "..."}` object. This representation is
   documented. The numeric branch has at most 603 decimal digits, below
   Python's minimum configurable guard of 640. Positive and negative
   `10**5000` build/JSON-roundtrip tests pass without changing the interpreter
   setting.

## Independent validation

- Static inspection of all modified production files and their callers:
  metadata remains source-registration-local; discovery uses `setdefault` to
  retain patches; frozen layers use an immutable mapping; validation precedes
  declaration/patch mutation. No runtime activation path was changed.
- Ranking is enabled explicitly only for injected singular dependencies and
  injected singular provider targets. It follows compilation, `when`, and the
  consumer filter. The stable linear maximum pass handles negative-only sets,
  retains maximum ties for the caller's warning/error contract, and preserves
  the all-zero path. Losing registrations remain compiled and validated.
- Definition-side parent masking is captured before the temporary parent view
  is restored. There is no parent score on the public component and no score
  propagation through children, decorators, or wrappers.
- Focused independent run: `uv run pytest -q tests/test_parent_precedence.py
  tests/test_boundaries.py tests/test_typed_providers.py
  tests/test_compiler_tooling.py tests/test_selection_census.py` — **236 passed
  in 2.50 seconds**, after both findings were fixed. The earlier run caught an in-progress test attribute typo;
  the corrected run passed.
- Independently executed the after runner, retaining reviewer output at
  `/tmp/parent_filter_review_after.json`: P1 **2/2**, P2 **6/6**, P3 uniquely
  selected `OrdersWait`; all runner assertions passed.
- Independently compared the recorded baseline with the after output: C1, C2,
  C3, G1, R1, and R2 retain identical winners, collections, parentless roots,
  preview availability, and warning codes. G2 retains exact collection
  membership/order for both orders; its singular choice may change as intended.
  G3 retains the fallback. Explicit R1 application override and explicit R2
  ordering pass the after runner's assertions.
- Additional direct compiler probes confirmed ordinary roots and runtime
  `Provider[T]` roots retain LIFO; marked `Provider[T]` roots retain
  `provider-ambiguous-component`; synchronous and asynchronous `use_component`
  declarations retain parentless LIFO while constructor injection selects the
  older preferred registration.
- Additional boundary probes confirmed an imported precedence `100` is neutral
  against local `-1` and `+1`: it wins the former and loses the latter. Captured
  evidence omits the imported effective value and records the local value.
  `Use.root` with two matches still fails with `boundary-use-ambiguous` despite
  a unique declared maximum.

The parent agent executed the supported-Python matrix and performance comparison;
those runs are separate from these independently executed checks. The final
[performance and compatibility report](14-parent-precedence-performance.md)
accurately distinguishes the older-version full runs from the final affected-path
reruns and the final Python 3.14 full CI.

## Performance evidence review

Applied the repository BenchBro skill and reliable-measurements guidance. Read
the benchmark source, fixed configuration, environment metadata, all four valid
raw JSON reports, and the final written interpretation. Independently recomputed
every results-table row from the arithmetic mean of each revision's two run
medians: all reported values match. Benchmark identities, iteration counts, and
repeat counts are consistent across the four runs. All 37 production source
hashes match the final candidate metadata. The invalid initial candidate snapshot
is explicitly excluded and contributes no reported timing.

The zero-precedence build controls (-2.46% to +1.85% in the chosen summary) do
not establish a repeatable regression, particularly given the disclosed opposing
results for the noisy 16-candidate control. The explicit build cases show a
plausible modest compilation cost (+1.87% to +5.19%, largest approximately
0.756 ms). The report correctly does not claim equivalent wiring for those
before/after cases, and uses a successful unique-eligible provider case rather
than comparing a failed baseline build with a successful candidate build.

Small runtime changes overlap observed control movement and do not establish a
meaningful runtime effect. This agrees with static confirmation that runtime
selection/activation code is unchanged. The evidence remains local, sequential
microbenchmark evidence: background load was uncontrolled, large application
graphs and allocations were not measured, and raw runs use BenchBro's default
`disable_during_measure` garbage-collection setting. It cannot prove zero overhead
or unchanged end-to-end memory/GC costs. No additional benchmark run is justified
by a specific unresolved concern here.

The measured compilation premium does not change the KEEP recommendation below.

## Usefulness assessment

**KEEP the explicit, opt-in design.** P1 improves from
1/2 to 2/2 installation orders and P2 from 1/6 to 6/6. P3 makes a uniquely
preferred injected provider usable without weakening tied-target ambiguity.
Those are concrete benefits for independently installed overlapping policies.
Disjoint rules, mutually exclusive fallbacks, identical-policy ties, hard
consumer filters, collection order, and immediate provider parents are controls,
not additional claimed improvements.

The cost is numerical coordination. A bundle that opts into `10` changes what a
later zero-valued application registration can override. Application owners must
know the bundle's policy, use an equal/larger value, patch their own declaration,
or explicitly filter at the consumer. Geography and privacy have no intrinsic
ordering; R2 correctly needs explicit policy or an ordinary tie. This design
does not eliminate coordination, but moves it from complete bundle installation
order or shared exception predicates into a small published priority contract.

The tradeoff is acceptable because omission remains zero with baseline behavior,
there are no inferred syntax weights or universal priority bands, and the change
does not expand into roots, collections, boundary cardinality, or runtime work.
Where one composition root already owns order or mutually exclusive rules, use
those existing mechanisms; the feature supplies no demonstrated benefit there.
The public documentation explains this limit and the application-override cost.
