# M04 implementation verification handoff

Status: Implementation and checks complete; independent review and coordinator checkpoint pending.
Implementation agent: `/root/m04_implementation`, `gpt-6-astra`, high reasoning.
Search: `/root/m04_search`, `gpt-6-luna`, low. Coordinator: `/root`.
Baseline: M03 final `530a725`; M04 search `f831e3a`; branch `codex/decorator-templates`.
The coordinator owns review records, execution log, status changes and all commits. This agent made no commits.

## Delivered interfaces

- New `clean_ioc/_decorator_templates.py` defines frozen `RegistrationInfo`, `DecoratorTemplate`, declaration,
  generated-candidate, source-selection evidence and expansion records. These remain internal/unexported until M05.
  Arguments and tags are defensively copied into immutable mappings/tuples. RegistrationInfo contains no instance
  or activation step. `implementation_bindings(base_type)` projects known static implementation evidence onto the
  base's actual TypeVars and returns an immutable mapping, preserving unresolved variables or returning `None`.
- `container.py` stores original template declarations, removal IDs and captured instance implementation evidence
  on `_Layer`. Private builder `_register_decorator_template`, `_patch_decorator_template`, and
  `_remove_decorator_template` support transactional declaration edits, preserving ID/shared decorator ordinal.
  No unusable public builder/protocol entrypoints were added. Ordinary decorator behavior is unchanged.
- `_BuilderBase._expand_decorator_templates(*, build_args=None)` materializes discovery, constructs the current
  root/overlay snapshot, normalizes aliases, prepares ordinary boundary visibility, and invokes the module-level
  `_expand_decorator_templates(prepared_blueprint, **compiler_inputs) -> _TemplateExpansion`.
  The module-level seam requires an already normalized, visibility-prepared snapshot; it receives the same build
  arguments, anchored singleton/preconfiguration steps, owners and inherited explanations as normal compilation.
- Expansion obtains exact visible service declarations through normal area visibility, excludes implementation-only
  lookup keys and implicit open-source specializations, and deduplicates original registration IDs. Explicit boundary
  aliases preserve the original definition-side service key. Each source compiles in its definition area through a
  fresh M01 disposable source compiler: complete, frozen, recursively undecorated, canonical parentless root.
  The source's own contextual condition is deferred to actual injection; dependency conditions remain enforced.
- Sources retain layer/visibility precedence and use declaration order within each layer, from the snapshot's insertion
  ordered origins. Explicit registrations precede discovery results. Generated records retain the template's shared
  ordinary-decorator ordinal and a separate source ordinal; M05 extends activation sorting with `-source_order`.
  Factory execution is once per matched identity/template/attempt, and generated IDs are
  `uuid5(UUID(template_id), source_registration_id)`. Different templates remain additive.
- `_TemplateExpansion` contains the prepared original blueprint, candidates, selections and immutable build arguments.
  Each candidate retains declaration, specification, RegistrationInfo, shared/source ordinals, declaration/source areas
  and owner tokens. Exact source arguments remain on the original registration in the retained blueprint; source
  evidence also retains the selected dependency graph. Generated candidates never enter builder declarations or
  ordinary decorator collections. Rejected-source evidence is retained without replaying predicates.
- Scoped owner-token reentry protection rejects mutation/build/preview/nested expansion from source filters and
  factories, including callbacks holding a retained boundary builder. `finally` resets the context after every attempt.
  Failed expansion discards partial generated output, preserves original declarations and chains its original cause.
  Source compilation failures retain their original code/path with template/source provenance, including real cycles.
- `_check_template_boundary_visibility(initial_prepared, expanded_normalized, *, build_args, candidates)` performs
  exactly one new preparation and compares ordered uses/exposes. Changed selections or newly invalid preparation
  raise `template-visibility-cycle`; newly invalid errors retain their original cause/path plus template/source IDs.
  Success preserves the agreed visibility with the expanded layers. No template callbacks or fixed-point replay occur.

## Static implementation evidence

The using-typetoolbox skill was applied. Identity-safe projection uses the accepted `_project_service_type` helper,
not GenericTypeMap's name-keyed representation. Tests distinguish closed constructor aliases, multilevel generated
subclasses, distinct same-name TypeVars, unresolved implementations, broad/closed/untyped factories, and existing
instances with `__orig_class__`. Factory annotations provide only the stated type; an absent/broad annotation never
implies a concrete family and factories are never activated.

Instance metadata is captured at registration without invoking the constant factory. Canonical source inspection
alone uses that known class for `Component.implementation_type`, allowing ordinary family filters to inspect known
instance types. Ordinary runtime Component normalization, dependency graphs, anchored steps and activation are
unchanged; the test explicitly verifies this difference. The metadata record preserves a known closed instance alias.

## Actual verification

New `tests/test_decorator_template_expansion.py`: **34 tests** for zero/two/same-class sources, immutable records,
source declaration/discovery ordering, composed graph filters, no activation, build arguments, contextual conditions,
exact closed aliases, generic implementations/factories/instances, late generic discovery, retry/repair, mutation and
build/preview reentry, private/imported/exposed visibility, stable source cycles, anchored resource arguments, private
overlay edits, and one-shot changed/ambiguous Use/Expose consistency checks.

Repository `.venv`, Python 3.14.4:

```
.venv/bin/python -m pytest tests/test_decorator_template_expansion.py tests/test_decorator_template_feasibility.py tests/test_service_targets.py tests/test_service_groups.py tests/test_boundaries.py tests/test_resource_ownership.py tests/test_compiler_tooling.py tests/test_closed_generic_constructors.py tests/test_registration_patterns.py tests/test_container.py tests/test_bundles.py tests/test_type_aliases.py tests/test_type_alias_lookup_paths.py -q --disable-warnings --maxfail=3
```

**481 passed in 3.84s**. Ruff check and ty check pass for the three changed Python files; Ruff format reports
**3 files already formatted**. `git diff --check` passes.

Existing Python 3.11 interpreter, isolated uv environment with pinned dependencies and no repository environment edits:

```
uv run --no-project --isolated --python 3.11 --with pytest==9.1.1 --with pytest-asyncio==1.4.0 --with funcie==0.2.0 --with typetoolbox==0.4.0 --with typing_extensions==4.16.0 python -m pytest tests/test_decorator_template_expansion.py tests/test_decorator_template_feasibility.py tests/test_service_targets.py tests/test_service_groups.py -q --disable-warnings --maxfail=3
```

**95 passed, 1 skipped in 0.24s**. The skip is the existing version-dependent PEP 695 case (passed on 3.14).
Initial fixture issues used a captive lifespan, an incorrect Use signature/default named filter, and an intentionally
redacted exception-message expectation; those were corrected. Source enumeration was corrected during implementation
from lookup precedence to accepted declaration order and covered directly. No unavailable checks counted as passes.

## M05 requirements and explicit limits

This milestone delivers bounded internal expansion, not generated target activation. `_compile_with_report` and public
build/preview are not yet wired to expand/activate templates. Successful ordinary plans retain original internal
metadata for overlay probes, but no public template registration API is exposed or advertised as usable.

M05 must consume these generated candidates alongside ordinary decorators, implement the complete group/DerivedServices
selector and generic decorated-argument behavior, evaluate generated `when` on the M01 undecorated occurrence snapshot,
and preserve exact source dependency selection/conditions. It must insert expansion after initial visibility and
outside diagnostic root retries, attach immutable generated/evidence output without replacing originals, then call
this consistency primitive with fully compiled generated semantics before fresh runtime compilation/public export.

The M04 consistency tests intentionally use **synthetic ordinary generated-equivalent decorators**. They prove the
one-shot comparison/cause/provenance primitive, not boundary correctness for real generated selectors. M05 must test
both group and DerivedServices generated semantics inside boundary compilation before exposing the API. Actual
activation cycles introduced by generated injection and their target/argument/provenance diagnostics also require
M05 integration; M04 tests real source cycles and retains M01's generated-equivalent activation probes.

No public explanatory docs changed, so the documentation comprehension gate is inapplicable. No bark-core source,
environment or commits changed. Unrelated work files and coordinator-owned milestone/log edits were preserved.
No full `make ci` or full supported Python matrix is claimed; these remain M10. Independent review and all checkpoint
SHAs are to be recorded by the coordinator before milestone acceptance.
