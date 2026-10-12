# 19 — Define explicit build and analyse contracts

Created: 2026-10-10\
Status: Complete — design reviewed; builder/composition decisions accepted; runtime implementation remains out of scope\
Assignment: `/root/graph_memory_task_19`, high reasoning\
Recommended reasoning effort: High (`high`)\
Prerequisites: [Investigation](build-and-analyse-investigation.md); consumer regression evidence

## Outcome

Replace `build(mode="run"|"analysis")` with `build()` and `analyse()`. Build emits
execution only: no custom rules, built-in validation passes, safety-policy audits,
or automatic diagnostic capture. Analyse performs the entire validation workflow.
Breaking changes are explicitly permitted; tasks 10/11's mandatory-build-rule
contract is superseded for this work.

Agreed follow-up: a single `add_validation_rule(rule)` API replaces the old
build-rule/validation-rule distinction. Remove the rule phase argument. All rules
run only during analyse. This decision is settled; implementation remains out of
scope for now, alongside the rest of tasks 19–25.

## Decisions and deliverables

- Specify return types for both root and scope builders. Build should return the
  ordinary executable container/scope, not a persistence artifact. Compare a
  dedicated analysis result owning report/graph/test-runtime with a rich runtime;
  record how partial failures, context management and retained owners work.
- Analyse completes every applicable rule before returning. Define aggregation,
  unavailable checks after compilation failure, and a report-read API that never
  executes callbacks. Do not require `validation_report()` to finish analysis.
- Set builder consumption/retry behavior. Prefer fresh composition factories for
  analysis and production, with no implicit analysis prerequisite or shared runtime
  singleton state. Decide whether same-builder sequential use is supported at all.
- Remove public mode/fine-grained policy flags and define the fate of `BuildMode`,
  `build_mode`, `build_report` and `validation_report`. Remove the old rule phase
  arguments as agreed; do not preserve two internal rule categories as a compatibility layer.
  No deprecation adapter is required. Do not return a fabricated successful
  validation report from an operation that performed no validation.
- Keep provider-root declaration and actual composition inputs distinct from policy.
  Decide explicit budgets/profiling/instrumentation without allowing them to trigger
  rich validation or introduce another build policy.
- Record where overrides/overlays live without retaining composition on ordinary
  execution runtimes. Set ordinary-scope inheritance and analysed test-runtime APIs.

## Required check inventory

Classify every existing rejection/check as analysis-only policy, wiring required
to emit instructions, or input/runtime-state behavior. Audit registration-time
checks too. Include captive dependencies, runtime-context captures, return types,
configured argument names, generics/aliases, visibility, provider ambiguity,
sync/async compatibility, per-call proxies, slots and warmups.

An execution-only compiler may fail because no target/instruction can be emitted.
It must not retain a validation pass under the label "essential safety". Prove the
boundary with representable-but-invalid cases that build successfully and analyse
rejects, plus genuine non-emittable cases that terminate build with a minimal error.
Do not weaken wiring, cleanup semantics or lifetime placement to bypass a policy.

## Acceptance

- A reviewed operation/capability/lifecycle table and error matrix with concrete examples.
- Explicit callback counts: zero validation callbacks in build; all applicable
  rules once per declared context per analysis; normal wiring callbacks remain.
- No hidden reconstruction, automatic analysis, analysis token or supported hybrid.
- Readiness changes for tasks 20–24 only after their dependent decisions are recorded.

Planning only. No runtime code or consumer changes are authorized by this item yet.

## Reviewed outcome

The [contract](19-contract.md), [source/check inventory](19-inventory.md) and
[result](19-result.md) specify a distinct `AnalysisResult`, one completed report,
single-attempt builders, explicit external composition ownership for overlays,
and a concrete policy-versus-emission boundary. On 2026-10-10 the maintainer
accepted the recommendations for single-attempt builders and explicit composition
ownership, including simplifying the latter to ordinary reference ownership with
no separate `close()` lifecycle. Structurally immutable composition must match the
parent runtime; ordinary scopes remain available without it. Consuming a builder
or moving data into a handle does not itself establish a memory saving.
Task 20 is ready for assignment. Tasks 21–24 retain their remaining implementation
prerequisites; none has started. The accepted design is not implementation or a
new benchmark result.
