# 03 — Python symbols and generated runtime constructs

Created: 2026-10-09\
Status: Not ready — symbol and reconstruction policy needs refinement\
Assignment: Unassigned\
Prerequisites: Task 02's feature inventory; task 06 for final codec integration

## Outcome

Reconnect the frozen plan to application types and executable runtime callables
without repeating registration discovery or graph compilation. Application code
is installed alongside the artifact; the artifact is not a replacement for it.

## Readiness and remaining decisions

- Choose the initial callable forms: importable classes/module-level functions
  are the proposed baseline. Explicitly decide bound methods, callable objects,
  closures, local functions, partials and application extension hooks.
- List supported type forms, including application closed generics, aliases,
  unions and annotated keys where the normal container supports them. Preserve
  existing normalization and type identity rather than inventing new lookup rules.
- Decide which generated types need compact reconstruction descriptions in the
  first subset, particularly generic decorators and per-call proxies.
- Define application import requirements and the supported symbol locator API.
  Do not require general callback serialization or capture arbitrary closures.

Record these choices and the permitted reconstruction operations before marking
implementation ready. Module-level symbol loading is a recommendation, not an
approved restriction on the whole library.

## Work

1. Classify all retained callables as build-only, runtime executable or generated
   runtime machinery. Freeze build-only results, including contextual selection,
   argument derivations and template expansion; discard their callback machinery
   where it is no longer used. Retained runtime filters need an explicit policy.
2. Define symbol references that resolve to the correct installed object, with
   clear errors for missing modules, moved symbols, unsupported callable forms
   and incompatible definitions. Coordinate code identity checks with task 06.
3. Define type-expression records for the agreed forms and verify identity in
   dependency keys, aliases, provider targets, maps and decorators.
4. Give supported generated runtime constructs deterministic reconstruction
   descriptions. Reconstruction may create a proxy class from frozen method
   information, but cannot rerun selection or discover dependencies.
5. Document import-side effects: application modules containing composition
   roots or environment-created instances may need separation from service
   definitions. Audit a fresh loader process to show which imports occur; Python
   imports execute module code and cannot be advertised as side-effect-free.
6. Keep compilation-only modules out of the required import list where practical.
   A separate runtime-only package/import path is a later measured optimization,
   not a prerequisite or an assumption that the current loader avoids all compiler
   imports.

## Verification and acceptance

- [ ] Importable types/functions round-trip in a fresh process with correct
  identity; supported generic and alias keys resolve equivalently.
- [ ] Every supported generated construct behaves equivalently, including
  method dispatch, scopes and cleanup where applicable.
- [ ] Unsupported symbols fail export with a dependency/declaration reference;
  load errors identify the missing or incompatible symbol.
- [ ] Guards demonstrate that imports/loading do not invoke composition entry
  points, template factories or build-only callbacks in the test application.
- [ ] Runtime factories still execute at their normal activation points and
  application import limitations are documented.

## Starting points

- `_symbol`, `_ALIAS_ORIGINS` and symbol encoding in the
  [artifact codec](../../benchmarks/graph_artifact.py).
- `_per_call_proxy_type` in [container.py](../../clean_ioc/container.py) and
  `create_generic_decorator_type` in [_legacy.py](../../clean_ioc/_legacy.py).
- [Generics documentation](../../docs/generics.md),
  [closed generic tests](../../tests/test_closed_generic_constructors.py) and
  [per-call scope tests](../../tests/test_per_call_scope_acceptance.py).
