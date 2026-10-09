# Pre-compilation

Created: 2026-10-09\
Status: Planning only — no implementation assigned\
Starting revision: `d51b6f5`

Develop the design for compiling a graph separately from the application process,
then loading its frozen resolution plan at startup. The current artifact loader
is an unfinished local experiment, not a supported persistence API.

The [artifact retest after graph-memory task 05](../graph-memory-optimization/artifact-retest-post05.md)
demonstrated the potential of reduced artifacts: the eight-route local fixture
loaded in 0.115 seconds with a 47.70 MiB process peak, versus 11.345 seconds and
127.83 MiB when compiling the same reduced runtime. These synthetic measurements
motivate further work; they do not establish production readiness.

## Tasks

| ID | Task | Readiness | What is needed next |
| --- | --- | --- | --- |
| 01 | [Unified container and scoped slots](01-unified-slots.md) | Not ready | Refine duplicate bindings, required inputs, ownership and overlay edge cases |
| 02 | [Feature coverage and first supported subset](02-feature-coverage.md) | Ready for investigation only | Inventory actual execution paths and propose the first supported subset |
| 03 | [Python symbols and generated runtime constructs](03-python-symbol-loading.md) | Not ready | Choose supported callable/type forms and generated-code reconstruction rules |
| 04 | [Frozen execution plans and fresh runtime state](04-frozen-plan-runtime-state.md) | Not ready | Audit mutable state and define ownership and reconstruction contracts |
| 05 | [Build inputs, constants and graph variants](05-build-inputs-and-variants.md) | Not ready | Decide embeddable values, late inputs and variant selection |
| 06 | [Artifact format, compatibility and packaging](06-artifact-format-and-packaging.md) | Not ready | Settle artifact contents, compatibility policy and the public build/load surface |
| 07 | [Loading, provisioning and startup](07-loading-and-startup.md) | Not ready | Define required-binding checks, startup transitions and warmup integration |
| 08 | [Diagnostics, explanations and runtime profiling](08-diagnostics-and-profiling.md) | Not ready | Choose supported reporting modes and compact profiling metadata |
| 09 | [Application equivalence and deployment measurements](09-application-validation.md) | Not ready | Select the application fixture, target image and acceptance criteria |

All tasks are unassigned and implementation has not started. Readiness is
separate from assignment or authorization to start work:

- **Ready for investigation only** means the evidence-gathering scope is concrete;
  implementation still requires the decisions recorded in that task.
- **Not ready** means a task needs design refinement, a maintainer choice or an
  unresolved prerequisite. Each task records the specific reason and the gate
  for becoming ready. This does not prevent read-only investigation of its open
  questions when that work is assigned.
- Mark a task **Ready for implementation** only after its decisions and required
  contracts are recorded. Do not treat proposed defaults as accepted decisions.

## Decisions and proposed first delivery

Agreed slot rules remain unchanged: a slot with `when` requires an explicit
stable binding, and ambiguous slot selection must fail before build success.
Task 01's readiness flag concerns its remaining edge cases, not those decisions.

The following recommendations still need review:

- Start with fixed composition and ordinary scopes; defer artifact-backed
  `ScopeBuilder` overlays. Compiled boundaries are a separate feature decision.
- Prioritize reduced explanation metadata and preserve the existing full/reduced
  resolution contract. Decide the supported reporting combinations in task 08.
- Build and package the artifact with the exact application and deployment image;
  regenerate it on incompatible changes. Cross-platform portability and format
  migrations are outside the proposed first delivery.
- Start with importable runtime symbols and a deliberately limited constant
  format. Application code remains a required deployment dependency.
- Never silently recompile when loading fails. Imports, loading, provisioning,
  warmup and serving have explicit responsibilities and failure points.

## Suggested sequence and dependencies

1. Complete task 02's inventory. Refine the slot contract in 01, symbol contract
   in 03 and value policy in 05; task 04's read-only state audit can inform them.
2. Agree task 06's artifact contract using those findings. Define which fields
   describe the frozen plan and which require fresh runtime state. Task 04's
   audit feeds this design; its loader integration follows the agreed format.
3. Implement the selected feature subset through tasks 01–07. Task 02 owns
   coverage of execution features not owned by the more specific tasks; it must
   name those cases before implementation. Tasks 03 and 05 supply symbol/value
   representations, 04 supplies runtime reconstruction, and 07 supplies startup.
4. Implement the agreed reporting/profiling subset in 08. It can be explicitly
   deferred from the first delivery only with a recorded capability decision.
5. Run task 09 against the completed subset. Select its application and image
   early so those requirements inform task 02 rather than arriving at the end.

Numbers group the work; they are not a strict implementation order. Design
findings may flow between tasks before implementation dependencies are complete.

## Design direction

- Keep dependency selection and graph compilation out of artifact loading.
- Separate frozen declarations and wiring from instances supplied by a running
  application. Environment-dependent configuration and clients must not be
  captured as live instances inside the artifact.
- Support the same slot contracts in normally compiled and loaded containers.
- Preserve the reduced runtime's memory benefits; explanation metadata stays
  optional, while metadata needed for resolution remains available.
- Keep previous experiments and their raw evidence intact. The tasks above
  turn the review into an explicit design and implementation backlog.

## Shared acceptance rules

- Loading restores frozen choices; it does not rebuild a registry, inspect
  dependency signatures, expand templates or rerun build-time selection,
  derivation or validation callbacks. Runtime filters and factories retain their
  ordinary execution semantics where supported.
- Test both behaviour and absence of accidental work: resolution results,
  sharing, cleanup and errors must match normal compilation for supported
  features, and compiler/activation guards must detect accidental work at load.
- Preserve aliases, type identity, shared steps and ownership relationships.
  Artifact-local references must be distinguished from fresh runtime identities.
- Each task names unsupported cases and produces useful export/load errors.
  The feature matrix must reflect actual codec and execution coverage, not just
  an allowlist or a successful round trip of the synthetic fixture.
- Public analysis reports retain the existing redaction and unversioned beta
  conventions in the parent work list. An executable artifact has different
  needs: task 05 must settle allowed constants, and task 06 must explicitly
  define private format compatibility without changing public report schemas.
- Preserve reduced-runtime memory savings. Measure optional reporting costs
  separately and keep compilation, imports, load, warmup and resolution distinct.
- Implementation tasks require focused semantic tests, applicable repository
  checks, executable documentation and a result report. Planning-only edits do
  not require a test-suite or benchmark run. No arbitrary performance target is
  assumed before task 09's criteria are reviewed.

The maintainer explicitly requested planning before implementation. Creating
these task documents does not start implementation, assign an agent or commit
to a production artifact format. API examples are proposals until implemented.
