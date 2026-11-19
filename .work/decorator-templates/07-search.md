# M07 search gate

Accepted read-only evidence from `/root/m07_search`, gpt-6-luna low; baseline `34f19e6`.

- `clean_ioc/tooling.py`: BuildIssue/BuildReport (~240), CompilationAttempt/PartialGraph (~367), CandidateDecision/CompilationExplanation (~97), GraphManifest (~892), CompiledGraph (~1057). Reuse frozen explanation sidecars and existing text/JSON renderers.
- `_decorator_templates.py`: immutable RegistrationInfo, generated definitions and _TemplateSourceSelection capture source identity, component/filter result, generated ID, order and areas. `_expand_decorator_templates` (~7115) retains these in the blueprint. They are not yet public inspection facts.
- `container.py:_compile_decorators` (~6150) selects group/DerivedServices targets and evaluates target filters; currently public decisions carry declaration origin without linked template/source/target definition and occurrence identities or generic projections. Capture facts here without reevaluation.
- `_safe_error_message` and `_filter_description` avoid arbitrary exception/closure contents. Preserve bounded partial graphs and stable candidate labels. Keep incidental provenance outside semantic manifests/fingerprints.
- `tests/test_compiler_tooling.py` covers explanation immutability, failure retries, redaction, CLI text/JSON, aliases and cross-process manifest stability. Template expansion/compilation/composition suites cover current runtime facts and failures.

Verification: successful/failed build explanations, exact source and target provenance, generic projections, filter decisions and overlaps, aliases/boundaries/order; sentinel private values absent from all output; inspection never replays callbacks; equivalent builds retain semantic fingerprints. Run tooling, template, manifest/failure regressions, Ruff/ty/format/diff and relevant Python3.11 portability checks.

No applicable AGENTS.md found. Search made no edits or commits. Coordinator inspected captured records, decorator compilation and existing tooling sidecars. M07 is bounded reporting work; preserve accepted runtime semantics. Public explanatory documentation remains M09.
