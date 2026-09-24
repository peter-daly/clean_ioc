# M07 implementation verification handoff

Status: round-2 Astra nested-overlay finding repaired and verified; coordinator repair checkpoint and same-reviewer recheck pending.
Agent: `/root/m07_implementation`, `gpt-6-sol`, high reasoning. Baseline: accepted M06/search checkpoint `4e9174a` on `codex/decorator-templates`. This agent made no commits. Coordinator owns status, log, checkpoint, and review.

## Delivered behavior

- `CompiledGraph.explain_template_sources(template_id=None)` returns immutable source-filter decisions in expansion order. Each records the template and source registration IDs, generated definition ID when selected, source service and static implementation label, inherited generic source substitutions keyed by declaring generic, captured filter description, origin, and declaration/source boundary. `TemplateSourceDecision` has text/JSON renderers. There is no callback or component-tree replay during inspection.
- `CompiledGraph.explain_decorators(core)` returns the compiler's captured target selection and `when` decisions even when no decorator attached. Its `CandidateDecision.template` sidecar distinguishes generated definition ID, template/source/target registration IDs, target occurrence ID, selector kind/contract, source and target generic bindings, projected contract, and target boundary. `graph.explain(generated_decorator)` also carries these facts. Selected overlapping independently declared template policies receive `template-policy-overlap` while retaining both definitions. Nonmember/unrelated selector candidates are rejected with `template-target-not-selected`.
- Source and target generic substitutions remain separately labelled by declaring generic; repeated TypeVar names within one generic get a stable positional suffix. Unknown source implementation metadata remains `None`, without runtime activation or argument inspection. Target selector/filter predicates run only during compilation. The frozen sidecars stay outside graph manifests and semantic fingerprints.
- Inherited anchored parent occurrences now copy and remap their frozen decorator and ordinary occurrence explanations into overlay graph occurrence IDs. Existing alias-aware root explanation and boundary origin/area metadata remain available.
- Generated selector/projection, `when`, materialization, and dependency failures include template/source/target context, target service, and the underlying build code. Source-filter and factory expansion failures name the failed phase and exception type in `BuildReport`, and their template/source IDs remain in the partial pre-graph witness. Original exception causes remain chained for local debugging; their text is omitted from reports. Failed expansion stops at the failing source, so later source choices do not exist to inspect.

## Files

Production: `clean_ioc/__init__.py`, `clean_ioc/_decorator_templates.py`, `clean_ioc/container.py`, `clean_ioc/tooling.py`.
Tests: new `tests/test_decorator_template_diagnostics.py` (9 tests). This handoff is the only M07 work-record file owned by the implementation agent. The coordinator's `execution-log.md` edit and unrelated untracked `.work` files were preserved.

## Verification

- Python 3.14 `.venv`: 598 passed in 5.14s across the new diagnostics, all template feasibility/expansion/compilation/composition suites, tooling, service targets/groups, boundaries, generic constructors/patterns, ownership, container/bundles, aliases, and complex dependencies.
- Isolated Python 3.11 (`uv run --no-project --isolated` with pytest 9.1.1, pytest-asyncio 1.4.0, funcie 0.2.0, typetoolbox 0.4.0, typing_extensions 4.16.0): 412 passed, 6 Python-version skips across diagnostics, template, tooling, service, boundary, generic constructor and pattern suites. Final rerun of the new file: 9 passed.
- Ruff check and ty check: pass for all four production files and new test file. Ruff format check: five files already formatted. `git diff --check`: pass.
- New cases cover successful/rejected source and target decisions, callback replay guards, group vs derived selection, separate generic identities, overlap, aliases, private boundaries, anchored overlay occurrence remapping, phase-aware pre-graph failures, secret redaction, and unchanged manifest serialization after inspection.

## Review focus and limits

Trace `TemplateDecision` construction in `_compile_decorators`, source capture in `_expand_decorator_templates`, graph freeze in `_finalize_plan`, and anchored remapping in `_clone_component_tree`. Check whether all error contexts remain privacy-safe and whether the extra inherited explanation maps retain only frozen records. The source-inspection component remains internal, and the public source decision exposes labels and IDs only. No bark-core changes, public explanatory docs/examples, or commits were made. M08 integration, M09 docs, and M10 full CI/matrix remain pending.

## Round-1 independent-review repairs

Reviewer `/root/m07_review` requested three P2 fixes in `07-review.md`. This implementation agent repaired them without committing:

1. Anchored cloning now chooses occurrence explanations, decorator explanations, parameter/generic facts, and definition origins by the source component's graph identity. Parent occurrence integers can collide with overlay integers; the parent sidecar now remains authoritative for parent components. The regression adds an overlay singleton source that shifts occurrence numbering, then checks core/decorator provenance and remapped target occurrence IDs.
2. Generated decorator materialization separates fixed compiler-authored validation errors from arbitrary exceptions raised during user-controlled introspection. It renders only the arbitrary exception's type, without invoking `__str__`; the original cause remains chained. The invalid-decorator report path also includes the target registration ID. A hostile `__signature__`/`__str__` regression proves that neither secret text nor formatting side effects reach the report.
3. Source-filter and template-factory callback phases now force compiler-owned `template-expansion` code and template/source path even if a callback raises `ContainerBuildError` with private code/path. A fixed internal reentry-guard exception preserves the existing `template-expansion-reentry` contract while never copying callback code/path. Both callback phases have redaction regressions.

Repair verification: 458 relevant Python 3.14 tests passed in 4.52s; isolated Python 3.11 had 364 passed and four existing version skips in 2.74s. Ruff check and ty check pass for the changed `container.py` and diagnostics test; Ruff format check passes after formatting; `git diff --check` passes. The repair changes only `clean_ioc/container.py`, `tests/test_decorator_template_diagnostics.py`, and this handoff. No reviewer acceptance is claimed until the same Astra reviewer rechecks the checkpoint.

## Round-2 nested-overlay repair

The reviewer accepted both privacy repairs but found that a grandchild overlay may clone an anchor whose `Component` still belongs to the root graph. Its immediate parent's occurrence-indexed sidecars can describe a different component at the same integer ID. Build-time inputs now collect each ancestor plan's frozen explanation sidecars keyed by its actual `_ComponentGraph` object. `_clone_component_tree` selects the exact owning graph for occurrence explanations, decorator decisions, origins, parameter records, and generic records; it never falls back to a sidecar from another graph. The five immediate-parent sidecar arguments were removed. The graph-keyed mapping exists only in transient compilation inputs and compiler instances, while the final plan keeps its own frozen records.

The shifted-ID regression now builds a grandchild overlay and checks template/source identity, remapped target occurrence IDs, and registration/decorator-template origins for both core and wrapper. Round-2 verification: **458 passed** in the affected Python 3.14 suites; isolated Python 3.11 **364 passed, 4 version skips**. Ruff check, ty check, format check, and `git diff --check` pass after formatting. No commits, public documentation, or bark-core changes by this agent. Reviewer acceptance remains pending.

## Final gate record

Accepted round3 by `/root/m07_review` (Astra High). Search `4e9174a`; implementation `d1d7ff7`; repairs `71183b8`, `6f454aa`; review `906452e`. Every checkpoint hook passed. Independent601 tests and five-generation shifted-ID probe passed; no unresolved findings. Original implementation agent was restored after transient capacity blockage. No public explanatory docs changed, so reader gate does not apply. Bark-core untouched; M08 may begin after final checkpoint.

## Verified checkpoint index

Coordinator completion audit; gate hashes resolve to local commit objects. The final M10 hash is filled after its commit.

| Gate | Outcome | Local commit |
| --- | --- | --- |
| Search | Passed | `4e9174a` |
| Implementation verification | Passed | `d1d7ff7` |
| Implementation verification, repair | Passed | `71183b8` |
| Implementation verification, repair 2 | Passed | `6f454aa` |
| Independent technical review | Passed round 3 | `906452e` |
| Final handoff | Passed | `2780e0e` |
