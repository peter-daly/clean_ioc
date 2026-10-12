# M01 code-search gate

Status: Passed; accepted by coordinator on 2026-09-23.

Agent: `/root/m01_search`; `gpt-6-luna`, low reasoning, fresh context, read-only.
Coordinator: `/root`. Initial clean-ioc HEAD: `520161b41bc35967a77b4bea0334e6fba9d62349`.
Working branch: `codex/decorator-templates`. No applicable ancestor/repository AGENTS.md found.
Initial working state: only the pre-existing untracked `.work/` directory. This task owns the decorator-template plan
and its milestone directory; the separate graph-information plans are unrelated and must remain unstaged.
Bark-core was clean at `b0cd55693889785a14be128d1f78f815f2a6e5fe`; no changes made there.

## Evidence map

- `container.py::_BuilderBase._layer` materializes queued discovery after explicit registration snapshots.
  `_RegistrationDiscovery.materialize` carries generic discovery into that snapshot. Explicit-before-discovered
  ordering and repeatable failed-build snapshots must remain intact.
- `_Layer`/`_Blueprint` retain private definitions; no suitable existing public immutable registration metadata view
  was found. `Component` is an occurrence view, not a definition view. Its service-oriented generic mapping is not
  sufficient for all inherited implementation bindings.
- `_compile_with_report` normalizes aliases and boundaries before `_Compiler.compile`; root compilation skips open
  generic definitions. `_compile_candidates` specializes and compiles candidate subtrees before contextual conditions.
- `_compile_registration` builds dependencies and calls `_compile_decorators`. The latter evaluates target `when`
  on the completed undecorated core before compiling decorators. This is the integration seam to preserve.
- `_Blueprint.decorators` / `_decorator_service_matches` currently select exact keys or the same generic origin;
  group members need a separate registered-service-to-contract projection, not runtime base-service aliases.
- `_preview_components` compiles a whole graph, including decorators, and is not a safe source-core-only shortcut.
  A source depending on a target can recursively require template expansion; M01 must prove safe staging/cycle handling.
- `component_filters.py` provides real Component predicates including descendants and parent. Source filtering cannot
  substitute a metadata object or execute application constructors to infer concrete types.
- `_specialize_factory`, `_specialized_component_id`, generic helpers and `_materialize_decorator` supply related
  mechanisms. Source and target TypeVars must remain distinct even when their names match. The typetoolbox skill warns
  its maps are internally name-keyed; do not merge independent binding domains through that representation.
- Existing decorator order is stored on definitions and sorted by position/layer/order; verify outside-to-inside
  behaviour through tests rather than assuming activation-order iteration matches display order.
- `ScopeBuilder.build` passes anchored parent singleton steps and owner tokens; source inspection and template
  expansion must not rewire those steps or bypass boundary-local visibility.

## Focused verification and handoff

Coordinator baseline: `.venv/bin/python -m pytest tests/test_provider_maps.py tests/test_closed_generic_constructors.py
tests/test_bundles.py -q --disable-warnings --maxfail=3` — **76 passed in 0.46s**, Python 3.14.4.
Imported clean_ioc is the working checkout. The search agent ran no tests or edits.

Useful suites: `test_container.py` for discovery/decorator/order/edit behaviour; `test_complex_dependencies.py` and
`test_closed_generic_constructors.py` for generic projection; `test_compiler_tooling.py` for filter errors, retries,
and singleton anchoring; `test_boundaries.py` and `test_resource_ownership.py` for ownership/visibility.

Implementation spike must prove: completed source-descendant filtering with no activation; deterministic handling of
a source-to-target expansion dependency cycle; generated concrete generic-source subclasses; independent same-named
source/target variables; anchored parent ownership and boundary-local source context; discovery identity/order on retry.
Resolve API spelling and retained blueprint metadata in the M01 decision record. Do not implement later milestones.

Search gate acceptance means the evidence map is sufficient to start the Astra High spike; it does not approve a
compiler design or certify the feature. Commit this gate before dispatching implementation.
