# M03 search gate

Accepted evidence: `/root/m03_search`, `gpt-6-luna`, low, read-only, baseline `fa33b7f`.

- `_Layer.service_groups` (`container.py:516`) and `_Compiler._service_groups_for` (4062) retain definition identity through `_specialize_factory` (4057). Shared selector should consume registration/layer/actual closed request, return contract projection and preserve request key.
- Explicit group selection checks membership first; DerivedServices projects the registered service contract, never implementation inheritance. Existing ordinary `_decorator_service_matches` (1635) and `_service_definition_matches` (985) are origin/exact matchers and must not change globally. `_public_service_matches` handles structural patterns.
- `_pattern_candidates` (4069+) and `_specialize_factory` provide specialized requests; deferred group validation must run when actual closed targets are selected, including generic constructors, factories, patterns, aliases, discovery and fallback. Keep snapshot state immutable and reject incompatible closed memberships clearly.
- M01 `generic_utils._project_service_type` (144–181) follows explicit bases with TypeVar identity, detects conflicting paths and preserves unresolved variables. Complete contract constraints and target selection around this seam. Existing name-keyed `_typevars_in`, factory resolver and typetoolbox maps cannot merge new identity-preserving bindings.
- Alias helpers: `normalize_type_alias`, `_normalize_blueprint_aliases`, `_blueprint_alias_errors`. M02 `_validate_service_groups` deliberately defers unresolved TypeVars, unions and Callable parameter lists; M03 completes those constraints for actual closed requests.
- Existing tests: feasibility projection cases (427–506), type aliases nested/reordered vars (61–88), closed generic constructors inherited reordering, service groups discovery retry and pattern ID retention, registration patterns.
- Project supports Python >=3.11,<4; Ruff/ty target3.11. PEP695 syntax fixtures must be version-conditional.

Verification baseline: M02 focused group/provider-map/pattern/constructor/container/alias/feasibility/boundary/bundle suites **322 passed**. Implementation should add concrete target selection tests for both selectors and all M03 requirements, then run these relevant regressions and Ruff/ty. No tests or edits by search agent; coordinator read generic helper and matching seams. Public docs and decorator activation remain later milestones.
