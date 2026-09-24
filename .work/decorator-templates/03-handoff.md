# M03 implementation verification handoff

Status: All applicable M03 gates passed; final local checkpoint required before M04.

Implementation: `/root/m03_implementation`, `gpt-6-astra`, high reasoning. Search: `/root/m03_search`, `gpt-6-luna`, low.
M02 accepted at `fa33b7f`; M03 search/implementation baseline `37a22f23a3c26824461ae1f55d0d56a99af21ad7`;
branch `codex/decorator-templates`. Coordinator owns commits, review, execution log and milestone status.

## Delivered

- `service_groups.py`/`__init__.py`: immutable public `DerivedServices(Contract)`.
- New `_service_targets.py`: shared explicit-membership/automatic-derived selection, frozen projection results and
  immutable identity-keyed bindings. Membership and nominal compatibility use registered service contracts, never
  implementation compatibility or structural protocol matching. No public aliases or registration discovery added.
- `generic_utils.py`: nested TypeVar-identity binding/substitution, correct `typing.Callable` rebuilding, nominal
  inheritance projection and clear ambiguous/unresolved failures. Using-typetoolbox skill applied; the new interface
  deliberately avoids its name-keyed mapping. Existing factory/decorator name-based machinery remains unchanged.
- `container.py`: original definition IDs retained through factory/pattern specialization; deferred group validation
  runs at `_compile_registration` against concrete requests. Finite candidate selection retains ordering and deduplicates
  by definition/request/owner. Ordinary decorator matching and activation are unchanged.
- New `tests/test_service_targets.py`: 30 cases covering equivalence of both selectors, nonmembers, immutable mappings,
  factories/instances without activation, unrelated-service and structural-protocol exclusion, nominal protocols,
  reordered/fixed/multilevel/repeated/same-name variables, generated classes, aliases, diamonds, closed-request builds,
  patterns, discovery/fallback, union/Callable constraints, ordering/deduplication, ordinary decorators and PEP 695.

## M04/M05 interface

`_Compiler._select_service_target(selector, registration, layer, requested_service_type)` consumes one already available
candidate and returns `_ServiceTarget | None`. The caller retains visibility/area/occurrence policy. Explicit nonmembers
are excluded before projection; automatic closed-contract mismatches return `None`. Errors include registration/request/
selector context, with `service-group-incompatible` or `service-target-projection` codes.

The frozen result fields are:

- `registration_id`: original definition ID, including for specialized factory/pattern copies.
- `requested_service_type`: untouched input request, including an explicitly supplied alias; the actual wrapped key.
- `registered_service_type`: normalized original registered contract. Closed declarations remain authoritative even
  through implementation lookup keys with different generic specializations.
- `projected_contract`: concrete specialization of the selector's contract origin.
- `bindings`: immutable origin-TypeVar-to-argument map.
- `declaration_bindings`: separate immutable bindings for variables in the selector expression. For `Contract[V, V]`
  over `Contract[int, int]`, this is `{V: int}`, while origin bindings retain `{T: int, U: int}`.

`_Compiler._select_service_targets(selector, candidates)` accepts finite `(registration, layer, request)` tuples,
keeps first-seen order and deduplicates original definition/canonical request/owner tuples. Call independently per
independent template. It neither discovers requests nor picks registry winners or grants boundary visibility.

`_bind_typevar_identities(pattern, concrete)` returns a TypeVar-keyed dictionary, `None` for mismatch, or raises
`_TypeBindingError` for ambiguous/unresolved/unsupported inference. M05 can bind a decorator's decorated-argument
expression to `target.projected_contract`, then use `_resolve_typevar_identities(annotation, bindings)`. Never merge
source/target/decorator scopes by name. M05 still owns remaining-variable validation and decorator activation.
For M04 source metadata, `_project_service_type(implementation, base)` remains the static projection seam, preserving
unresolved variables; pair projected arguments with the base origin's actual `__parameters__`. Unknown factory
implementation types remain unknown without activation.

## Actual verification

Repository `.venv` Python **3.14.4**:

1. `.venv/bin/python -m pytest tests/test_service_targets.py tests/test_service_groups.py tests/test_provider_maps.py tests/test_registration_patterns.py tests/test_closed_generic_constructors.py tests/test_container.py tests/test_type_alias_lookup_paths.py tests/test_type_aliases.py tests/test_decorator_template_feasibility.py tests/test_boundaries.py tests/test_bundles.py -q --disable-warnings --maxfail=3`
   — **352 passed in 2.14s**.
2. `.venv/bin/ruff check clean_ioc/_service_targets.py clean_ioc/generic_utils.py clean_ioc/service_groups.py clean_ioc/container.py clean_ioc/__init__.py tests/test_service_targets.py` — **passed**.
3. `.venv/bin/ty check clean_ioc/_service_targets.py clean_ioc/generic_utils.py clean_ioc/service_groups.py clean_ioc/container.py clean_ioc/__init__.py tests/test_service_targets.py` — **passed, no diagnostics**.
4. `.venv/bin/ruff format --check clean_ioc/_service_targets.py clean_ioc/generic_utils.py clean_ioc/service_groups.py clean_ioc/container.py clean_ioc/__init__.py tests/test_service_targets.py` — **6 files already formatted**.
5. `git diff --check` — **passed**.

Existing Python **3.11.13** interpreter, isolated temporary uv environment (no repository dependency/lockfile edits):

`uv run --no-project --isolated --python 3.11 --with pytest==9.1.1 --with pytest-asyncio==1.4.0 --with funcie==0.2.0 --with typetoolbox==0.4.0 --with typing_extensions==4.16.0 python -m pytest tests/test_service_targets.py tests/test_service_groups.py tests/test_decorator_template_feasibility.py -q --disable-warnings --maxfail=3`

— **57 passed, 1 skipped in 0.18s**. The sole skip is version-conditional PEP 695 syntax; it passed on 3.14.
Early fixture failures incorrectly reused successful builders or expected pattern entrypoint marking to create a request;
fixtures were corrected without changing those existing behaviours. Full matrix/`make ci` remain M10.

## Limits and pending review

- M03 delivers selection/projection and deferred membership checks, not template expansion/activation or public docs.
  Existing lookup rules decide which registrations are available; no broadening of open-alias or pattern lookup.
- ParamSpec/TypeVarTuple inference fails explicitly. TypeVar domains require nominally checkable class constraints;
  uncheckable parameterized/protocol domains fail clearly. Complete decorator/default handling remains M05.
- Union-variable matching uses unique disjoint partitions, including multiple members absorbed by one variable.
  Multiple assignments fail as ambiguous; required union collapse (`T | int` inferred from `int`) fails explicitly.
  Fully concrete equivalent unions remain order-insensitive. Legacy factory/decorator union behaviour is unchanged.
- No public explanatory documentation changed; comprehension gate inapplicable. No bark-core files/environment changes
  or commits. Unrelated graph plans and coordinator-owned work-item edits remain untouched.
- No implementation-agent commits. Independent review requested the repairs below; coordinator records actual review findings,
  repairs, acceptance and checkpoint SHAs. This handoff does not claim final milestone acceptance.


## First-review repairs

All three P2 findings repaired; same-reviewer recheck pending:

- Union binding uses complete supported assignments first, then a separate collapse-only diagnostic pass if none
  succeeds. An abandoned nested collapse alternative no longer poisons the valid `T -> bytes` assignment.
- Inherited expressions normalize aliases before substitution and path comparison. Equivalent aliased diamonds agree;
  generic nested aliases specialize correctly while retaining distinct same-name variable identities.
- A possible collapse to a smaller union (`T | int | str` against `int | str`) reports unsupported inference, including
  through `DerivedServices`. Actual fixed-member mismatches still return nonselection. Collapse diagnosis requires a
  complete otherwise-compatible assignment, so a later conflicting argument cannot leave a false diagnostic behind.

Added four regression cases in `test_service_targets.py` (34 total). Repeated the exact focused/portability/check commands
above: Python 3.14 **356 passed in 2.16s**; Python 3.11 **61 passed, 1 expected PEP 695 skip in 0.19s**; Ruff, ty,
format (**6 files**) and diff checks passed. No commits, public documentation or bark-core changes from this repair turn.

## Final handoff

Independent Astra High `/root/m03_review` accepted repaired implementation `daa8871` in round2; review checkpoint `c652a5f`. Search checkpoint `37a22f2`, initial verification `60cf3a2`, repair verification `daa8871`; all full-unit/lint/type commit hooks passed. Final SHA recorded after commit in execution log. No public docs gate applies. M04 consumes the selector/projection and identity-binding interfaces above, plus accepted M01 source-core inspection and visibility consistency staging. No remaining M03 blockers; explicit supported-inference limits remain as documented. No bark-core edits or commits, unrelated graph plans preserved.
