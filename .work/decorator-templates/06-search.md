# M06 search gate

Accepted read-only `/root/m06_search`, `gpt-6-luna`, low; baseline `d62c87e`.

- Definite gap: `_preview_components` (`container.py:8583`) uses only local layer/boundaries; ScopeBuilder.build (8668) includes parent layers/inherited boundaries and all anchor/owner/explanation inputs. Unify effective snapshot/compiler inputs for build/preview/internal expansion so scope previews match actual compilation without final validation side effects.
- `_compile_with_report` (7227) expands once outside retries; generated output stays separate from original layered templates. Parent singleton anchor branch must remain unchanged at runtime; current expansion-only overlay tests do not certify wrapped-object/cleanup behavior.
- `_find_decorator_template` (8230) searches local/inherited root policy only; boundary template IDs intentionally private. Patch replace preserves ID/order but stores override locally. Removal tombstones suppress inherited IDs. Ordinary decorator patch (8372) follows same layer-local convention; test deterministic actual order with patched inherited and local declarations, including ordinal collisions, and document established semantics in internal handoff.
- Generated target applicability is declaration-area local, source enumeration uses ordinary Use/Expose visibility. Shared groups grant no access. Add private-source/target negatives, legal import/export and explicit source aliases, no root editing private boundary templates.
- Runtime acceptance gaps: new-source/new-target overlays, nested overlays, named target overrides with/without explicit membership, anchored parent singleton wrappers/resources/cleanup graph agreement, plain scopes no callbacks, public patch/remove/other-family independence, failed-build repair and retry deduplication.
- Existing tests: template compilation and expansion, boundaries, resource ownership, container, bundles. Existing expansion overlay probes use inactive decorators/private APIs and must be complemented with actual runtime wrapper assertions.

Coordinator read template edits and scope/boundary contract; preserve existing visibility and named-registration selection rules rather than inventing source shadowing. Complete M06 scope only, no public docs or bark-core work. Search performed no edits/tests.
