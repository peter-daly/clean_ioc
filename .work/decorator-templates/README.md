# Decorator templates — sequential milestones

Status: Executing sequentially. M01–M02 accepted and committed; M03 implementation in progress. M04–M10 remain pending.

[Feature contract](../decorator-templates.md) is the source of truth for behaviour and constraints.
This directory replaces that work item's broad implementation sequence with independently reviewable milestones.
The earlier graph-information roadmap in `../README.md` is a separate project; its model assignments do not apply here.

## Run order and model assignments

Complete these milestones strictly in order. Each passed gate requires a local clean-ioc checkpoint commit before
the next gate starts. Start the next milestone only after all predecessor gates pass and their commits are recorded.
Every row uses three distinct agents: a code-search agent, an implementation agent, and an independent review agent.

| ID | Milestone | Code search | Implementation recommendation | Review | Dependency |
| --- | --- | --- | --- | --- | --- |
| 01 | [Contract and compiler feasibility](01-contract-and-feasibility.md) | Luna Low | Astra High | Astra High | None |
| 02 | [Explicit service-group membership](02-service-groups.md) | Luna Low | Sol High | Astra High | 01 accepted |
| 03 | [Generic projection and DerivedServices](03-target-selection-and-generics.md) | Luna Low | Astra High | Astra High | 02 accepted |
| 04 | [Source filtering and template expansion](04-source-filtering-and-expansion.md) | Luna Low | Astra High | Astra High | 03 accepted |
| 05 | [Decorator compilation and activation](05-decorator-compilation.md) | Luna Low | Astra High | Astra High | 04 accepted |
| 06 | [Composition edits, scopes, and boundaries](06-scopes-boundaries-and-edits.md) | Luna Low | Astra High | Astra High | 05 accepted |
| 07 | [Diagnostics and inspection](07-diagnostics-and-inspection.md) | Luna Low | Sol High | Astra High | 06 accepted |
| 08 | [Local bark-core integration proof](08-bark-core-test-bed.md) | Luna Low | Astra High | Astra High | 07 accepted |
| 09 | [Standalone documentation and comprehension](09-documentation.md) | Luna Low | Sol High | Astra High + fresh Luna Low reader | 08 accepted |
| 10 | [Regression checks and completion](10-final-verification.md) | Luna Low | Sol High | Astra High | 09 accepted |

Exact agent settings:

- Luna Low: `model="gpt-6-luna"`, `reasoning_effort="low"`.
- Sol High: `model="gpt-6-sol"`, `reasoning_effort="high"`.
- Astra High: `model="gpt-6-astra"`, `reasoning_effort="high"`.

Model assignments are recommendations based on each milestone's risk, not measured performance guarantees.
Use Astra for cross-cutting compiler/generic/ownership reasoning and Sol for bounded work after the contracts settle.
These choices are consistent with [OpenAI's model guidance](https://developers.openai.com/api/docs/guides/latest-model)
and supported [reasoning settings](https://developers.openai.com/api/docs/guides/reasoning), checked 2026-09-23.
The user's prescribed search/review roles remain fixed. Do not silently fall back to another model if one is unavailable.

## Per-milestone workflow

1. **Search:** spawn a fresh Luna Low agent with `fork_turns="none"`. Supply this workflow, the milestone, feature
   contract, previous handoff, and exact repository paths. Its task is read-only: locate current code, tests, applicable
   repository instructions, reusable helpers, and relevant constraints. Return an evidence map with paths/symbols and
   likely verification commands. Search findings are leads for implementation, not architectural approval.
2. **Implement:** spawn a separate agent at the model/effort listed above, also with an explicit handoff rather than
   inherited conversation. Supply the contract, milestone, evidence map, and predecessor's accepted decisions.
   Only this agent edits feature code for the milestone. It implements the bounded scope and runs appropriate checks.
   Record actual files, checks/results, limitations, and decisions. Do not implement later milestones opportunistically.
3. **Review:** spawn a separate Astra High agent with `fork_turns="none"`. Supply the requirements, bounded change set
   or diff, evidence, and test results. It independently inspects code/tests and checks relevant regressions, ownership,
   generic identity, and stated limits; it does not merely approve the implementer's summary. Return actionable findings
   with file/line references and an accept/request-changes verdict.
4. **Resolve:** the implementation agent fixes findings. The same reviewer checks the revised change set. Resolve all
   blocking findings; explicitly disposition lower-priority findings before acceptance. A reviewer who implements a
   substantial fix must hand acceptance to a fresh Astra High reviewer.
5. **Documentation gate:** whenever a milestone changes public explanatory docs or examples, run the additional
   [fresh-reader protocol](documentation-review.md). M09 always requires it. The code-search agent cannot double as the
   documentation reader. No code reviewer or implementation agent can substitute for the fresh reader.
6. **Final handoff:** record all gate outcomes, checkpoint commit SHAs, and remaining limitations. Complete the final
   handoff gate and commit its evidence before advancing to the next milestone. This final commit does not replace
   the commits required after earlier gates.

## Local commit after every passed gate

This applies inside every milestone, including feasibility, documentation, integration, and final verification:

| Gate | Pass condition | Local clean-ioc checkpoint content |
| --- | --- | --- |
| Search | Coordinator accepts the requested evidence map as complete | Task-owned search findings and bounded implementation handoff |
| Implementation verification | Milestone scope delivered and its applicable checks pass | Implementation, tests, and actual check evidence; independent review is still pending |
| Independent technical review | Astra High accepts, with blocking findings resolved | Review repairs, relevant verification results, and acceptance record |
| Documentation comprehension, when applicable | Fresh-reader review and later quiz pass the documented rubric | Documentation repairs, validated examples, and internal reader/quiz acceptance evidence |
| Final handoff | All applicable gates and checkpoint commits verified | Milestone completion record and next-milestone handoff |

The fresh reader's initial review and subsequent quiz are two phases of one comprehension gate: do not coach the reader
between them. A failed gate is not marked passed or committed as acceptance. After repairs, rerun its required checks
and commit when it passes; retain earlier checkpoint history. If a later change invalidates an earlier accepted gate,
reopen that gate, recheck it, and create a new checkpoint on its next pass.

For each checkpoint, stage only that gate's task-owned clean-ioc deliverables and evidence. A read-only search or review
gate still produces an evidence record to commit; never manufacture an empty commit. Use descriptive messages such as
`docs: record service-group search findings (M02 search)` or `feat: add explicit service groups (M02 verification)`.
An implementation-verification commit is explicitly a checkpoint awaiting independent review, not final approval.

Inspect the staged diff first; exclude unrelated edits, temporary reader packets, secrets, and task files belonging
to other work. Never use a blanket staging command on the pre-existing untracked `.work/` directory. Never include
bark-core source copies in checkpoint evidence. Record the gate, its actual result, and resulting commit SHA before
advancing. Use `NN-handoff.md` and `NN-review.md` once work actually runs; do not create fictitious results now.
The resulting SHA can be recorded in the coordinator log/post-commit handoff without amending a commit merely to
include its own hash. Verify HEAD and git status after committing. Do not push, squash, amend unrelated commits,
or start the next gate/milestone until the local commit succeeds. If blocked, report the actual blocker.

Use the collaboration agent tools for these roles, not separate sidebar tasks. This workflow requests future milestone
execution roles; splitting the plan does not itself start feature implementation. Do not pre-spawn later milestone
agents or let concurrent writers cross milestone boundaries.

The three roles are sequential within a milestone too: search, implementation, review. They are not a request to run
dependent work in parallel. For repairs reuse the implementation agent and reviewer while retaining independence.
The currently available four slots are sufficient, including the coordinator. Retire completed roles before adding new ones.

## Common gates and constraints

- Remain in the clean-ioc working checkout unless isolation is needed. Capture initial repository state and preserve
  unrelated edits. Every passed milestone gate ends in a local clean-ioc commit; publishing, pushing, and releasing are
  outside this instruction. No milestone is complete before all its passed gates have recorded checkpoint commits.
- bark-core is an authorized local integration test bed only. Never create task commits there. Track task-owned edits
  and any dependency override separately; do not reset unrelated user changes.
- Public documentation must be independently authored from the Clean IoC contract. Do not reference, copy, or adapt
  bark-core code, identifiers, conventions, or composition examples. Internal integration notes remain separate.
- Keep source filters and target `when` as ordinary component filters. Keep explicit membership and automatic
  `DerivedServices` selection distinct. Preserve generic identities, visibility, and immutable runtime composition.
- Intermediate milestones may deliver internal helpers or metadata before the feature is usable end to end.
  Keep existing checks green; do not expose a knowingly broken public feature as complete or use permanent xfails to
  mask incomplete requirements. M05 is the first end-to-end path, M06 supplies required composition semantics.
- Changes to API spelling are resolved in M01 and propagated through this contract, tasks, and tests. Later discoveries
  may amend the plan with evidence, but may not silently drop an accepted user requirement.
- After later fixes revisit affected earlier acceptance cases, not every previous check indiscriminately.
  No skipped or unavailable check counts as passed. Finish the full required suite in M10.

## Completion record

Every handoff must name the model/effort and agent identities, baseline/change boundaries, delivered behaviour,
checks actually run, review findings and resolution, any documentation reader/quiz evidence, local commit SHA per gate,
and remaining limitations.
Bark-core handoffs must also list every task-owned file/environment change and confirm no task-created commits.
All ten milestones and applicable documentation gates must be accepted before marking the feature complete.
