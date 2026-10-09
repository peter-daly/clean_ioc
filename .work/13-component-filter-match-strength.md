# 13 — Component-filter match strength (retired)

Status: Retired by the maintainer on 2026-09-27\
Experimental branch: `codex/scored-component-filters`\
Base: `version2` at `63cbea4` (`2.0.0b23`)\
Replacement: [14 — Parent-context registration selection](14-parent-context-registration-selection.md)

## Decision

Drop automatic strength ranking of ordinary dependency filters. A precise
filter already identifies its intended registration, and a simple conjunction
usually gives every eligible candidate equal strength. Scoring boolean
alternatives introduced preference semantics that were not justified by the
ordinary dependency-selection use case.

Restore boolean component filters and the existing LIFO selection rules. Start
again with the narrower case where different registrations declare different
parent-context applicability policies.

## Preserved experiment

The implementation, design notes, review report, tests, and benchmark source
were saved together in a local Git stash before restoring the base:

```text
9df0e848bf56e6bcd1831cbe9b1c5972e424afbf
On codex/scored-component-filters: Retired component-filter scoring experiment; restart parent filtering 2026-09-27
```

That stash includes untracked files. Its immutable object ID identifies the
snapshot even if later stashes change its `stash@{n}` position. Recover it only
in a separate checkout or branch so it does not mix with the replacement work.
Raw benchmark/compatibility artifacts remain under the ignored local directory
`.benchbro/match-strength.jwi6cmfu/`.

The experiment passed checks and independent review; the decision to retire it
is about design value and complexity. It was not committed to the development
branch, published, or released. Its `MatchStrength`, `FilterExpression`, and
ranked runtime-root API are not part of the replacement branch.
