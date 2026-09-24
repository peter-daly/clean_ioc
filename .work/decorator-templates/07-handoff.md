# M07 implementation verification handoff

Status: implementation delivered and verified; independent Astra review and coordinator checkpoint pending.
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
