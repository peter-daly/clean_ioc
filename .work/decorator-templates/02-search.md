# M02 search gate

Accepted read-only evidence from `/root/m02_search` (`gpt-6-luna`, low). Baseline `485e27d`.

- Add an immutable identity declaration alongside the ProviderMapGroup pattern (`provider_maps.py:14`); export from `__init__.py`. Keep membership out of the group object.
- `_BuilderBase.register` (`container.py:7227`) is the shared class/factory/instance path. Materialize and validate groups before mutating legacy registration; store frozen membership by definition ID, separate from provider-map contributions.
- `_BuilderBase` metadata at 7082 and `_layer` at 7128–7162 provide builder/snapshot seams. `_Layer` and alias normalization must preserve membership.
- `register_pattern` (7303) forwards groups; pattern specialization (3847–3963) changes IDs and records `_pattern_sources`. Membership must be explicitly reachable from specialized definitions. Ordinary generic specialization preserves IDs.
- `_RegistrationDiscovery` (1874–1943) must carry immutable groups to subclass, generic subclass and fallback definitions. Queue APIs (7659–7734) and `components.ComponentBuilder` signatures require additions. Discovery uses temporary registries and cached definition objects; validate before publishing membership/cache state and preserve retry stability.
- Use M01 `_project_service_type` for nominal registered-service compatibility; reject unrelated/conflicting projections. Concrete closed arguments must match; origin-only `_service_definition_matches` is insufficient. Retain genuinely unresolved constraints for M03.
- Existing reference tests: provider maps identity/transactionality, container discovery timing/retry/overlays and factory specialization, closed generic constructors, public protocol signatures.

Implementation assignment: M02 only, per `02-service-groups.md` and accepted `01-handoff.md`. Add focused tests covering all declaration paths, one-shot generators, independent builders, same-name group identities, repeated memberships, aliases, known closed argument mismatch, transactional rejection, discovery/fallback and specialized metadata. Verify ordinary resolution/provider maps remain unchanged. Public explanatory docs are reserved for M09.

No source edits or tests performed by the search agent. Coordinator inspected direct registration and discovery seams. Search findings are accepted for implementation, not as architecture or code acceptance.
