from pathlib import Path
p=Path('clean_ioc/container.py'); s=p.read_text()
s=s.replace('''    def build_report(self) -> BuildReport:
        return self._plan.build_report''','''    def build_report(self) -> AnalysisReport:
        if self._plan.build_report is None:
            raise RuntimeError("Execution runtimes have no analysis report; use a fresh builder.analyse()")
        return self._plan.build_report''')
s=s.replace('            runtime._install_observation(instrumentation.profiler, fingerprint, labels, paths)','            cast(_ObservedScope, runtime)._install_observation(instrumentation.profiler, fingerprint, labels, paths)')
# Retain source-backed evidence from non-fatal policy errors.
s=s.replace('    rule_outcomes: list[AnalysisRuleOutcome] = field(default_factory=list)\n','    rule_outcomes: list[AnalysisRuleOutcome] = field(default_factory=list)\n    evidence: dict[int, FailureEvidence | None] = field(default_factory=dict)\n    unknown_checks: list[str] = field(default_factory=list)\n',1)
start=s.index('    if error.report is not None:',s.index('def _analysis_issue')); end=s.index('\n\ndef _analyse_check',start)
s=s[:start]+'''    if error.report is not None:
        issues = error.report.issues
    else:
        issues = (BuildIssue(
            code or error.code or "analysis-check-failed", IssueSeverity.error,
            _safe_error_message(error), root=error.path[0] if error.path else None, path=error.path,
        ),)
    state.issues.extend(issues)
    for index, issue in enumerate(issues):
        if index < len(error.evidence):
            state.evidence[id(issue)] = error.evidence[index]


def _analysis_factory_compatibility(result_type: Any, service_type: Any) -> bool | None:
    state = _ANALYSIS_STATE.get()
    if state is None:
        raise RuntimeError("Factory compatibility is analysis-only")
    result = factory_result_compatibility(result_type, service_type)
    if result is None:
        state.unknown_checks.append(f"Factory return assignability is unknown for {qualified_name(service_type)}")
    return result
'''+s[end:]
s=s.replace('factory_result_compatibility(result_annotation, registration.service_type)', '_analysis_factory_compatibility(result_annotation, registration.service_type)')
s=s.replace('factory_result_compatibility(result_annotation, specialized.service_type)', '_analysis_factory_compatibility(result_annotation, specialized.service_type)')
# Remove dead old runner entirely.
start=s.index('def _validation_rule_issues('); end=s.index('def _run_validation_rules(',start); s=s[:start]+s[end:]
# Rules cannot leak snapshots into ordinary result serialization via missing coverage metadata.
s=s.replace('''            analysis.plan = finalized
            analysis.graph = finalized.compiled_graph''','''            analysis.plan = replace(finalized,
                selected_registrations=_selected_registration_catalogue(finalized), slots=blueprint.slots,
                ensured_import_modules=tuple(dict.fromkeys(name for layer in (*blueprint.layers, *(b.layer for b in blueprint.boundaries)) for name in layer.ensured_import_modules)))
            analysis.graph = finalized.compiled_graph''',1)
s=s.replace('''AnalysisStageOutcome("built-in checks", "completed"),''','''AnalysisStageOutcome("built-in checks", "completed"),
                        *(AnalysisStageOutcome("factory return assignability", "unknown", detail)
                          for detail in dict.fromkeys(analysis.unknown_checks)),''',1)
# Locate report evidence in finalizer (deduplicated uses state).
needle='''_issue_failure_evidence(issue) if issue._origin is not None else None for issue in deduplicated'''
s=s.replace(needle,'''state.evidence.get(id(issue), _issue_failure_evidence(issue) if issue._origin is not None else None)
            for issue in deduplicated''',1)
# Preserve completed executable plan even if a rule budget prevents complete analysis.
s=s.replace('''                None,
                self._owner_token,
                getattr(self, "_parent", None),
            )
        finally:
            _ANALYSIS_STATE.reset(token)''','''                state.plan,
                self._owner_token,
                getattr(self, "_parent", None),
            )
        finally:
            _ANALYSIS_STATE.reset(token)''',1)
# Early preparation failures still enumerate rules; snapshot them without evaluating declarations.
needle='''        state = _AnalysisState()
        token = _ANALYSIS_STATE.set(state)'''
s=s.replace(needle,'''        parent = getattr(self, "_parent", None)
        inherited = () if parent is None else parent._plan.blueprint.validation_rules
        state = _AnalysisState(definitions=(*inherited, *self._validation_rules,
            *(rule for boundary in self._boundaries for rule in boundary._validation_rules)))
        token = _ANALYSIS_STATE.set(state)''',1)
p.write_text(s)
