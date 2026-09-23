# M02 implementation verification handoff

Status: All applicable M02 gates passed; final local handoff checkpoint required before M03.

Implementation agent: `/root/m02_implementation`, `gpt-6-sol`, high reasoning. Search evidence: `/root/m02_search`, `gpt-6-luna`, low reasoning, accepted at search checkpoint `9cb82d7`. Branch: `codex/decorator-templates`. Predecessor M01 final checkpoint: `485e27d`. The coordinator owns checkpoint commits, review, execution log, and final status; this agent made no commits.

## Delivered

- `clean_ioc/service_groups.py` defines immutable, identity-equal `ServiceGroup(name, *, service_type=...)`. The declaration stores no members; its name and contract appear in errors. `clean_ioc/__init__.py` exports it.
- `groups: Iterable[ServiceGroup] = ()` is present on concrete and `ComponentBuilder` protocol registration methods for direct class, factory, instance, structural pattern, subclass discovery, and generic-subclass discovery. Inputs are consumed once and deduplicated by identity before registration state changes.
- Builder and immutable layer snapshots retain frozen membership by definition ID, separate from `ProviderMapGroup` contributions. Discovery records membership for each generated definition and fallback. Alias normalization retains group identity and revalidates canonical services. Compiler-local factory/pattern specializations retain membership against their generated IDs. Independent builders and overlays have separate membership maps; an override receives only its own declarations.
- M01 `_project_service_type` validates nominal registered-service compatibility, ambiguous projections, and concrete generic argument conflicts, including nested arguments, before direct registry mutation and before discovery candidates enter the discovery cache. Implementation class compatibility alone never grants membership. Open TypeVar constraints and genuinely unresolved aliases remain deferred to the M03 interface. In particular, a later closed request for an open definition still needs M03 validation.
- Existing resolution and provider-map behavior remain unchanged. No decorator-template selection or execution was implemented.

## Verification

Executed in this checkout with `.venv` Python 3.14.4:

1. `.venv/bin/python -m pytest tests/test_service_groups.py tests/test_provider_maps.py tests/test_registration_patterns.py tests/test_closed_generic_constructors.py tests/test_container.py tests/test_type_alias_lookup_paths.py tests/test_type_aliases.py tests/test_decorator_template_feasibility.py tests/test_boundaries.py tests/test_bundles.py -q --disable-warnings --maxfail=3` — **322 passed in 2.06s** after the second review repair. Fourteen new M02 tests cover export/protocol signatures, all registration forms, one-shot generators, identity and independent builders, concrete/nested generic rejection, transactional direct and discovery rejection, aliases, fallback, snapshots, overlays, specialized pattern IDs, equivalent unions, unresolved union constraints, unresolved `Callable` parameter TypeVars, ordinary resolution, and provider maps.
2. `.venv/bin/ruff check clean_ioc/container.py clean_ioc/components.py clean_ioc/service_groups.py clean_ioc/__init__.py tests/test_service_groups.py` — **passed**.
3. `.venv/bin/ty check clean_ioc/container.py clean_ioc/components.py clean_ioc/service_groups.py clean_ioc/__init__.py tests/test_service_groups.py` — **passed**.
4. `git diff --check` — **passed**.

Public explanatory documentation was not changed; the documentation comprehension gate is inapplicable. No bark-core files or environments were changed and no bark-core commits were made. Pre-existing unrelated `.work` graph plans were left untouched. Full `make ci`, supported Python matrix, and bark-core integration remain later-milestone gates.

## Review boundary

Independent reviewer should inspect whether membership survives every definition ID path and alias/overlay normalization, direct and discovered validation is transactional, and open generic constraints are explicitly deferred without claiming closed specialization safety. The coordinator will record review findings, repairs, checkpoint SHAs, and final M02 acceptance separately.

First independent review requested two P2 repairs in `_known_group_type_conflict`: order-insensitive equivalent union arguments were rejected, and the parameter list in `Callable[[T], int]` was treated as one opaque value instead of deferring its TypeVar. The first repair accepts equal concrete types first and recursively compares list/tuple argument sequences. New regressions confirm different concrete union members and concrete `Callable` input/return conflicts still reject.

The same reviewer then found that positional comparison still rejected `Service[T | int]` under `Service[int | str]`, although `T=str` can satisfy it. The second repair checks open union members for possible matches on either side and defers unresolved alternatives to M03; a fixed member with no possible counterpart still rejects. A regression covers the accepted open union and rejected concrete or fixed-member conflicts. The focused **322-test** suite, Ruff, ty, and `git diff --check` all pass after this repair. Same-reviewer recheck remains pending.

## Final handoff

Independent Astra High `/root/m02_review` accepted at `156abd5` in round 3. Review checkpoint `64958b4`. Search checkpoint `9cb82d7`; initial implementation `799d528`; verified repairs `541f611` and `156abd5`. All checkpoint full-unit/lint/type hooks passed. Public documentation gate inapplicable. Final handoff SHA recorded after commit in execution log.

M03 consumes `_Layer.service_groups` and `_Compiler._service_groups_for(registration, layer)`; the latter accounts for compiler-local structural-pattern IDs. `_validate_service_groups` rejects known conflicts at declaration/normalization, while unresolved TypeVars, Callable parameter lists and satisfiable open union constraints remain deferred. M03 must enforce these constraints against actual closed target requests and supply a common explicit-group/DerivedServices projection interface. No template execution delivered yet. No bark-core changes or commits; unrelated graph plans preserved.
