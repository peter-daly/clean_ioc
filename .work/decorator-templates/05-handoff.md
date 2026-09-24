# M05 implementation verification handoff

Status: All applicable M05 gates passed; final checkpoint required before M06.
Implementation: `/root/m05_implementation`, `gpt-6-astra`, high reasoning.
Baseline: accepted M04 `596e12a`, search checkpoint `e6bd146`, branch `codex/decorator-templates`.
Coordinator owns checkpoint commits, review, status and execution-log changes. No commits made by this agent.

## Delivered interfaces and behavior

- `_Blueprint.generated_decorators` and `.template_selections` retain immutable expansion candidates/evidence separately
  from original `_Layer.decorator_templates`. `_compile_with_report` expands exactly once after alias normalization and
  ordinary visibility preparation, outside diagnostic compiler retries. It normalizes the expanded snapshot, runs the
  actual generated boundary consistency check, then compiles with a fresh compiler. Runtime resolution/graph inspection
  does not replay factories, source filters or target predicates. Preview follows the same expansion/compilation path,
  while preserving existing preview semantics that exclude final validation-rule execution.
- Concrete builders and `ComponentBuilder` expose `register_decorator_template`, `patch_decorator_template` and
  `remove_decorator_template`. `DecoratorTemplate` and `RegistrationInfo` are exported from `clean_ioc`. Private M04
  probe aliases remain for its tests. Root patch/remove and preview now operate on working generated behavior.
- `_compile_decorators` consumes real group/DerivedServices selectors through the M03 registration-based projection,
  preserving exact target definition/request identity. Generated materialization binds the decorated argument to the
  projected contract, independently substitutes source-specialized aliases, and rejects unresolved/conflicting types.
  Callable results are checked against that projected contract including concrete generic arguments. The actual wrapped
  request remains unchanged. The using-typetoolbox skill was applied: new binding maps use TypeVar identity throughout;
  original signature annotations are read before legacy name-based dependency inference can alter them. Existing
  generic specialization classes and ordinary activation plumbing are reused after bindings have been resolved.
- Generated dependencies retain normal argument policies (including `select(cf.with_id(source.id))`), conditions,
  visibility, configured source dependencies, lifespan and ownership. Source selection failure never substitutes another
  registration. Common decorator activation provides sync/async success/failure cleanup. Generated activation cycles
  retain `circular-dependency` and append template/source/target provenance; invalid arguments retain template/source IDs.
- Ordinary/generated definitions sort together by `(position, layer_index, -order, -source_order)`. Earlier source
  declarations are outermost within one template; ordinary declaration order/positions remain compatible. Distinct
  templates remain additive. Membership and descendant multiplicity produce no duplicated layers.
- Generated target predicates share one recursively undecorated frozen view per eligible occurrence, and make no view
  for ineligible occurrences. `_undecorated_component_view` now follows relevant parent/dependency/preconfiguration/
  decorated/owner links, preserving contextual facts while excluding attached decorator branches. The scale probe
  excludes 80 unrelated roots and verifies snapshot reuse, actual parent/argument context, and unchanged ordinary
  decorator visibility of decorated descendants. M01's owner/frozen-graph probes remain green.
- Actual generated group and DerivedServices decorators participate in boundary metadata compilation before publication.
  Eight Use/Expose probes cover changed ordered selection and newly ambiguous selection, preserved original cause and
  template/source path, and exactly one factory call. These replace synthetic-only evidence for fundamental safety.

## Changes

`clean_ioc/container.py`, `components.py`, `_decorator_templates.py`, `__init__.py`; new
`tests/test_decorator_template_compilation.py` (**42 cases**); existing expansion tests updated for the now-public
entrypoints and to keep the internal overlay metadata fixture's deliberately non-activatable decorator inapplicable.
No public explanatory docs/examples or bark-core files/environment changed.

## Actual verification

Python 3.14.4 repository environment:

```
.venv/bin/python -m pytest tests/test_decorator_template_compilation.py tests/test_decorator_template_expansion.py tests/test_decorator_template_feasibility.py tests/test_service_targets.py tests/test_service_groups.py tests/test_boundaries.py tests/test_resource_ownership.py tests/test_compiler_tooling.py tests/test_closed_generic_constructors.py tests/test_registration_patterns.py tests/test_container.py tests/test_bundles.py tests/test_type_aliases.py tests/test_type_alias_lookup_paths.py tests/test_complex_dependencies.py -q --disable-warnings --maxfail=3
```

**537 passed in 4.16s.** Includes two independent source families; either/both/neither target resources; exact instances,
source/declaration order and filters; groups/nonmembers/DerivedServices; nested resources and decorator-only exclusion;
ordinary positions/additive templates; generic constructor/factory/instance/open/pattern requests for both selectors;
partially source-specialized aliases with independent same-name TypeVars; projected callable results; invalid arguments;
preview/patch/remove; configured singleton source identity; activation cycles; sync/async success and failure cleanup.

Existing isolated Python 3.11 interpreter, no project environment modifications:

```
uv run --no-project --isolated --python 3.11 --with pytest==9.1.1 --with pytest-asyncio==1.4.0 --with funcie==0.2.0 --with typetoolbox==0.4.0 --with typing_extensions==4.16.0 python -m pytest tests/test_decorator_template_compilation.py tests/test_decorator_template_expansion.py tests/test_decorator_template_feasibility.py tests/test_service_targets.py tests/test_service_groups.py -q --disable-warnings --maxfail=3
```

**139 passed, 1 skipped in 0.50s.** The existing PEP695 version-dependent case is the skip; it passes on 3.14.
Ruff check and ty check pass for all six changed/new Python files. Ruff format check: **6 files already formatted**.
`git diff --check` passes. Initial fixture API mistakes (pattern request publication/entrypoint spelling) were corrected;
no public request availability was widened. The broader run caught preview validation callbacks; preview now skips plan
finalization, preserving the existing regression. No unavailable check is represented as passing.

## Limits and next milestone

Root end-to-end behavior and actual fundamental boundary feedback safety are delivered. Full overlay composition edits,
boundary aliases, anchored ownership and inherited-template acceptance remain M06. In particular the pre-existing base
builder preview constructs a local-only blueprint; overlay preview parity is not claimed here. Detailed generated
inspection/diagnostics are M07, local integration is M08, public explanatory documentation is M09, and full CI/matrix
completion is M10. No release-readiness claim or public documentation comprehension gate applies to this milestone.
Original declarations are retained so M06 can re-expand against each overlay's current sources; generated candidates are
never appended as declarations. Independent review findings/acceptance and checkpoint SHAs remain coordinator-owned.

## Independent-review repairs

Round 1 requested three P2 repairs; all are implemented, with same-reviewer recheck pending. Repair files are
`container.py`, `test_decorator_template_compilation.py`, and this handoff. No commits made by the implementation agent.

1. Removed the flattened MRO projection map. Constructor annotations now use only the projection onto the class
   defining `__init__`; runtime implementation arguments come independently from the source's own class projection.
   Four regressions cover overridden/inherited constructors and open/closed decorator aliases reusing the same TypeVar
   through `Base[list[T]]`. They assert selected auxiliary instances and actual runtime `Wrapper[int]`/`Base[list[int]]`
   projections, detecting the previously wrong double specialization.
2. Added `_resolve_decorator_defaults`, a local identity-keyed default graph resolver. Defaults are transitive,
   independent of argument order, discover referenced variables absent from direct annotations, and reject cycles.
   Only default edges recurse; the M01 single-edge inheritance substitution helper remains unchanged. Automatic
   decorated-argument inference now uses the existing ordinary shape predicate before identity unification, so a bare
   defaulted TypeVar dependency is not mistaken for the wrapped contract. New tests cover both default-chain shapes,
   cycle rejection, and portable `typing_extensions.TypeVar` without a default. Both typing/typing_extensions NoDefault
   sentinels are respected, including their difference on Python 3.11.
3. Generated `when` failures now raise `decorator-filter-failed` with target/template/source path and exception type,
   retaining the original exception as cause without including its potentially private message. The probe verifies
   provenance in BuildReport and failed PartialGraph attempts, original cause identity, and no source/factory replay
   through diagnostic retries. Ordinary predicate exception handling remains unchanged.

Re-ran the exact focused and Python 3.11 commands above after repairs: Python 3.14 **546 passed in 4.35s**, including
**51 generated compilation cases**. Python 3.11 **145 passed, 4 skipped in 0.54s**: the existing PEP695 skip plus three
explicitly version-gated stdlib TypeVar-default tests (all pass on 3.14). The extensions NoDefault portability test
passes on both interpreters. Ruff check, ty check, format check (**6 files already formatted**) and diff check pass.
No public docs, bark-core changes, commits, or M06 implementation were included in these repairs.

## Final handoff

Independent Astra High `/root/m05_review` accepted repair `f9cbaee` in round2; review checkpoint `636205b`. Search `e6bd146`, initial verification `1c508ea`, repair `f9cbaee`; all full-unit/lint/type commit hooks passed. Final SHA recorded after commit in execution log. Public docs gate inapplicable. M06 must complete overlay preview/build parity, inherited template/source/target additions and edits, visibility aliases and anchored ownership acceptance. No remaining M05 blockers, no bark-core edits/commits, unrelated work preserved.
