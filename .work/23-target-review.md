# Item 23 target-keyword API follow-up — independent review

Status: complete — **APPROVE / KEEP**. The superseding public API is consistently
implemented as `declare_slot(..., target="scoped"|"container")`; the former
`declare_scope_slot()` method and `scope=` keyword are absent. Runtime slot
selection, ownership and provisioning semantics are unchanged.

Scope: the focused API migration following the initial item 23 approval. This
review inspected the builder implementation and protocol, active repository
callers, ASGI/FastAPI bundles, tests, benchmarks, executable-doc source, README,
upgrade/changelog material, marketing example and packaged Library Skills.
Historical work records, benchmark snapshots, installed environments and raw
source hashes were treated as preserved evidence rather than active callers. The
reviewer made no production edits; this file is the only reviewer-authored change
for the follow-up.

## Finding and repair

1. **Fixed — stale public demo used the removed method.**
   `marketing/LAUNCH_PLAN.md` still showed
   `builder.declare_scope_slot(RequestContext)` in its 20-second demo. It now uses
   `builder.declare_slot(RequestContext, target="scoped")`. A final active-tree
   scan finds the legacy name only in intentional removal prose and assertions.

No other actionable finding remains.

## Contract review

- `ComponentBuilder`, `ContainerBuilder`, `ScopeBuilder` and `BoundaryBuilder`
  expose the same keyword-only, required `target` parameter and have no
  `declare_scope_slot` attribute.
- Omitting `target`, passing `scope=`, or combining `target=` with `scope=` raises
  `TypeError`; an unsupported target value raises the documented `ValueError`.
- Internal `_SlotInput.scope` ownership metadata remains unchanged, as intended;
  this migration affects declaration spelling only.
- Implicit declarations are uniformly unique. Repeating one locally or in an
  inherited overlay fails with `duplicate-slot` in execution builds and
  verification. No idempotent compatibility path remains.
- ASGI and FastAPI bundles retain their once-per-class, per-builder guard. Shared
  ASGI setup is declared once on one builder, ordinary overlays inherit it, and
  reapplying a framework bundle in an inheriting overlay fails rather than
  silently redeclaring inputs.
- Active tests, scripts, benchmarks, integrations, public guides, README,
  upgrade guide and packaged Library Skills use `target=`. Historical `.work`,
  `.benchbro`, cache and installed-environment copies remain unchanged by design.

## Independent validation

- Unified-slot plus ASGI/FastAPI integration suite: **104 passed**, with the one
  existing FastAPI/Starlette `httpx` deprecation warning.
- Direct verification probe confirms an inherited implicit redeclaration returns
  a report containing `duplicate-slot`.
- Runtime signature inspection confirms the required keyword-only parameter and
  removed method on all four public builder surfaces.
- Focused Ruff, `ty check clean_ioc`, and `git diff --check`: passed.
- Final current-environment `make ci` passed on Python 3.14.4 with **2,610
  tests** and the existing FastAPI/Starlette warning. It includes Ruff, format,
  type checking, executable documentation and benchmark discovery. The unified
  suite has **83 cases**; strict MkDocs and executable docs also pass separately.
- The implementation owner recorded follow-up hashes in
  `.work/23-target-source-hashes.json` and appended validation to
  `.work/23-validation.txt`, preserving the original delivery snapshots. The
  earlier supported-Python matrix and performance experiment were intentionally
  not repeated for this spelling-only change.

## Verdict

**APPROVE / KEEP.** The requested breaking migration is complete, explicit and
internally consistent. It leaves no compatibility alias or old keyword path,
updates active consumers, preserves bundle composition behavior, and does not
alter the reviewed runtime slot contract.
