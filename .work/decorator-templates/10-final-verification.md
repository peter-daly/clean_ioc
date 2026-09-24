# 10 — Regression checks and completion

Status: Final verification passed locally; independent Astra review pending. Dependency: 09 accepted (`9734712`), fresh reader20/20.
Read the [workflow](README.md), feature contract, all accepted handoffs, and M09 technical/quiz evidence.

| Role | Model | Reasoning |
| --- | --- | --- |
| Code search | gpt-6-luna | low |
| Implementation | gpt-6-sol | high |
| Independent review | gpt-6-astra | high |

Sol High is recommended for a bounded acceptance/check pass after the high-risk behaviour has been independently reviewed.

## Bounded outcome

Verify the final combined implementation, close evidence gaps, and leave an accurate reviewable completion record.
No new feature scope or public release is included.

## Search assignment

Map every feature-contract acceptance row to tests/hand-off evidence; check actual CI/Makefile/pre-commit requirements,
supported Python matrix, public exports, docs examples and changes since M09. Identify coverage/check gaps, not speculative
new requirements. Recheck bark-core working state and task-owned changes.

## Implementation assignment

- Fill meaningful acceptance gaps and repair regressions. If a repair changes an earlier contract or high-risk compiler
  stage, return it to that milestone's review gate and recheck affected evidence before completion.
- Run required clean-ioc checks, including `make ci` and required pre-commit hooks. Verify actual command definitions.
  Report local version/platform coverage separately from CI matrix coverage; do not claim unexecuted CI passed.
- Confirm M08 integration evidence remains valid for the final code. Re-run affected focused tests when intervening
  changes justify it; do not repeat unrelated broad suites solely for activity.
- Validate public docs contain no bark-core reference/adaptation and still match final API spellings. Any documentation
  change triggers the applicable fresh-reader process; stale quiz results cannot certify revised docs.
- Record final file/change summary, tests and limitations, all review verdicts, and a clear task-owned bark-core ledger.

## Verification and review gate

Astra High reviews the combined feature against the parent contract and verifies every milestone's acceptance evidence.
Mark the feature complete only after unresolved blocking findings are fixed and required available checks pass.
Any unavailable check remains explicitly unverified; distinguish whether it blocks completion.
Confirm no task-created bark-core commits, no lost unrelated changes, and no runtime compilation/filter reruns.

Update milestone/parent status only with actual results. Leave release/publishing and any bark-core migration outside scope.
Follow the shared checkpoint-commit policy for each gate of this milestone too, and verify that the handoffs record
every passed gate's commit SHA across all milestones.
