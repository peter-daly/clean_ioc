from pathlib import Path
import ast,textwrap
P=Path('clean_ioc/container.py'); s=P.read_text()
def rep(a,b,n=1):
    global s
    assert a in s,a[:100]
    s=s.replace(a,b,n)
# One rule declaration category. Old public vocabulary removal beyond this surface is task24.
rep('    ValidationRuleMode,\n','')
rep('    mode: ValidationRuleMode\n','')
rep('def add_validation_rule(self, rule: ValidationRule, *, mode: ValidationRuleMode = "build") -> None:', 'def add_validation_rule(self, rule: ValidationRule) -> None:')
rep('"""Add a synchronous graph rule to the build or validation phase."""','"""Add a synchronous graph rule evaluated once by analyse()."""')
rep('        if mode not in ("build", "validation"):\n            raise ValueError("mode must be \'build\' or \'validation\'")\n','')
rep('                rule,\n                mode,\n','                rule,\n')
rep('    BuildIssue,\n','    AnalysisReport,\n    AnalysisRuleOutcome,\n    AnalysisStageOutcome,\n    BuildIssue,\n')
# Ambient analysis state is scoped to a single admitted operation, including its subcompilers.
anchor='class BuilderAlreadyBuiltError(RuntimeError):'
new='''@dataclass(slots=True)
class _AnalysisState:
    issues: list[BuildIssue] = field(default_factory=list)
    rule_outcomes: list[AnalysisRuleOutcome] = field(default_factory=list)
    definitions: tuple[_ValidationRuleDefinition, ...] = ()
    graph: CompiledGraph | None = None
    plan: _PlanSet | None = None


_ANALYSIS_STATE: ContextVar[_AnalysisState | None] = ContextVar("clean_ioc_analysis", default=None)


def _analysis_active() -> bool:
    return _ANALYSIS_STATE.get() is not None


def _analysis_issue(error: ContainerBuildError, *, code: str | None = None) -> None:
    state = _ANALYSIS_STATE.get()
    if state is None:
        return
    if error.report is not None:
        state.issues.extend(error.report.issues)
    else:
        state.issues.append(BuildIssue(
            code or error.code or "analysis-check-failed", IssueSeverity.error,
            _safe_error_message(error), root=error.path[0] if error.path else None,
            path=error.path,
        ))


def _analyse_check(callback: Callable[..., Any], *args: Any, code: str | None = None, **kwargs: Any) -> None:
    """Run a pure policy check only inside analyse, preserving a failed finding."""
    if not _analysis_active():
        return
    try:
        callback(*args, **kwargs)
    except ContainerBuildError as error:
        _analysis_issue(error, code=code)
    except (TypeError, ValueError) as error:
        _analysis_issue(ContainerBuildError(str(error), code=code or "invalid-declaration"))


'''
rep(anchor,new+anchor)
# Pure checks have no compilation responsibilities. Call them only for analysis.
for name in ['_validate_dependency_names','_validate_per_call_implementation']:
    tree=ast.parse(s); changes=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id==name:
            start=sum(len(x) for x in s.splitlines(True)[:node.lineno-1])+node.col_offset
            end=sum(len(x) for x in s.splitlines(True)[:node.end_lineno-1])+node.end_col_offset
            call=ast.get_source_segment(s,node.value)
            changes.append((start,end,'_analyse_check('+name+', '+call[len(name)+1:]))
    for start,end,value in sorted(changes,reverse=True): s=s[:start]+value+s[end:]
# Runtime-context calculation is needed even when no policy audit runs.
rep('    def _validate_runtime_context_dependency(', '    def _runtime_context_lifespan(')
rep('self._validate_runtime_context_dependency(', 'self._runtime_context_lifespan(',99)
# Captive and conformance checks report without aborting otherwise emittable instructions.
policy_codes={'captive-dependency','captive-resolution-context','captive-runtime-scope','provider-requires-async','managed-provider-requires-async','provider-captive-scope','per-call-sync-activation','async-required'}
tree=ast.parse(s); lines=s.splitlines(True); offsets=[0]
for line in lines: offsets.append(offsets[-1]+len(line))
changes=[]
for node in ast.walk(tree):
    if not isinstance(node,ast.Raise) or not isinstance(node.exc,ast.Call) or not isinstance(node.exc.func,ast.Name) or node.exc.func.id!='ContainerBuildError': continue
    code=next((kw.value.value for kw in node.exc.keywords if kw.arg=='code' and isinstance(kw.value,ast.Constant)),None)
    conditional=next((kw.value for kw in node.exc.keywords if kw.arg=='code' and isinstance(kw.value,ast.IfExp)),None)
    if code not in policy_codes and not (conditional and {getattr(conditional.body,'value',None),getattr(conditional.orelse,'value',None)} <= policy_codes): continue
    if node.lineno>12000: continue
    start=offsets[node.lineno-1]+node.col_offset; end=offsets[node.end_lineno-1]+node.end_col_offset
    changes.append((start,end,'_analysis_issue('+ast.get_source_segment(s,node.exc)+')'))
for start,end,value in sorted(changes,reverse=True): s=s[:start]+value+s[end:]
# Avoid running the captive proof at all in build; the method has no semantic return.
rep('        retention_frames = self._retention_frames()\n', '        if not _analysis_active():\n            return\n        retention_frames = self._retention_frames()\n')
# Avoid traversing provider targets for safety proofs in build.
rep('if capturing_singleton is not None:\n                forbidden', 'if _analysis_active() and capturing_singleton is not None:\n                forbidden')
rep('if capturing_singleton is not None and not managed:\n                forbidden','if _analysis_active() and capturing_singleton is not None and not managed:\n                forbidden')
# Actual computation returns effective lifespans, but no audit-only retention scan in build.
rep('        if service_type in (ResolutionContext, legacy.CurrentGraph):\n', '        if not _analysis_active():\n            if service_type in (ResolutionContext, legacy.CurrentGraph):\n                return "transient" if bool(getattr(parent.implementation, _ACTIVATION_LOCAL_CONTEXT_ATTRIBUTE, False)) else "per_resolution"\n            if service_type in (Scope, legacy.Scope, legacy.Resolver, legacy.ScopeCreator):\n                return "scoped"\n            return "singleton" if service_type is Container else "transient"\n        if service_type in (ResolutionContext, legacy.CurrentGraph):\n')
# Factory proof is never evaluated during execution compilation.
rep('factory_result_compatibility(result_annotation, registration.service_type)', 'factory_result_compatibility(result_annotation, registration.service_type) if _analysis_active() else None')
rep('factory_result_compatibility(result_annotation, specialized.service_type)', 'factory_result_compatibility(result_annotation, specialized.service_type) if _analysis_active() else None')
rep('        occurrence = (\n            issue._occurrence_path[-1]', '        if not _analysis_active():\n            return\n        occurrence = (\n            issue._occurrence_path[-1]')
# Supplied provider values are ordinary value instructions, not forced provider bindings.
start=s.index('        if provider is not None:\n            valid_policy',s.index('    def _compile_dependency(')); end=s.index('        policy_code = "argument-default"',start)
s=s[:start]+'''        if provider is not None:
            injected = isinstance(policy, _SelectArgument) or (
                policy is default_parameter_value_factory and dependency.default_value is legacy.EMPTY
            )
            if injected:
                return self._dependency_alias_result(
                    self._compile_provider_dependency(dependency, parent, *provider),
                    declared_type, dependency.service_type,
                )
'''+s[end:]
# Declaration storage must not reject policy-invalid values.
rep('        if scope == "per_call" and instance is not None:\n            raise ValueError("scope=\'per_call\' cannot be used with instance=")\n','')
rep('        if new_scope == "per_call" and component_id in self._instance_implementation_types:\n            raise ValueError("scope=\'per_call\' cannot be used with instance=")\n','')
rep('        if root_policy == "entrypoint" and getattr(service_type, "__parameters__", ()):\n            raise ValueError("root_policy=\'entrypoint\' requires a closed service type")\n','')
rep('        _validate_service_groups(service_type, service_groups)\n','')
start=s.index('                group_service_type = _composition_type(group.service_type)',s.index('    def register(')); end=s.index('                normalized_contributions[group]',start)
s=s[:start]+s[end:]
# Deferred group proof; actual projection in template selection remains binding semantics.
start=s.index('                try:\n                    _validate_service_groups(canonical_service'); end=s.index('            normalized_registrations',start)
s=s[:start]+'''                _analyse_check(_validate_service_groups, canonical_service,
                               layer.service_groups.get(registration.id, ()), code="service-group-incompatible")
                if _analysis_active():
                    for group in layer.contributions.get(registration.id, ()):
                        if not _service_definition_matches(canonical_service, _composition_type(group.service_type)):
                            _analysis_issue(ContainerBuildError(
                                "Registration service is incompatible with its provider map contribution group",
                                code="provider-map-group-incompatible", path=(qualified_name(canonical_service),)))
'''+s[end:]
rep('                        or registration.lifespan != legacy.Lifespan.transient\n','')
rep('"transient lifespan, and no argument overrides"','"and no argument overrides"')
# Unused membership is not a required projection. Validate projection only during analyse.
rep('        for group in sorted(groups, key=lambda item: (item.name, self._qualified_name(item.service_type))):\n            self._select_service_target(group, registration, layer, requested_service_type)', '        if _analysis_active():\n            for group in sorted(groups, key=lambda item: (item.name, self._qualified_name(item.service_type))):\n                _analyse_check(self._select_service_target, group, registration, layer, requested_service_type)')
# Boundary topology/duplicate/style checks do not decide actual instruction identity.
rep('if not isinstance(boundary.name, str) or boundary.name == "root" or not _BOUNDARY_NAME.fullmatch(boundary.name):', 'if not isinstance(boundary.name, str) or boundary.name == "root":')
rep('        for exposure in boundary.exposes:\n            if exposure.alias is None:', '        if _analysis_active() and not _BOUNDARY_NAME.fullmatch(boundary.name):\n            _analysis_issue(ContainerBuildError("Invalid boundary name style", code="boundary-invalid-name", path=(boundary.name,)))\n        for exposure in boundary.exposes:\n            if not _analysis_active() or exposure.alias is None:')
rep('    cycle = _boundary_cycle(blueprint.boundaries)', '    cycle = _boundary_cycle(blueprint.boundaries) if _analysis_active() else None')
# Convert individual boundary policy failures; retain ambiguous distinct exposures as wiring failures.
for phrase in ['"BoundaryAlias generic variables must map one-to-one between source and public services"', 'f"Boundary use cycle:', 'f"Boundary {boundary.name!r} uses the same component more than once"', 'f"A decorator or pre-configuration in {label} targets only a component across a boundary"']:
    idx=s.index(phrase); start=s.rfind('raise ContainerBuildError(',0,idx)
    tree=ast.parse(s); target=next(n for n in ast.walk(tree) if isinstance(n,ast.Raise) and n.lineno==s[:start].count('\n')+1)
    end=sum(len(x) for x in s.splitlines(True)[:target.end_lineno-1])+target.end_col_offset
    s=s[:start]+'_analysis_issue('+ast.get_source_segment(s,target.exc)+')'+s[end:]
rep('            if key in selected_keys:\n', '            if key in selected_keys:\n')
needle='''                ))
            selected_keys.add(key)
'''; rep(needle,'''                ))
                continue
            selected_keys.add(key)
''')
rep('public_identities: set[tuple[Any, str | None, tuple[legacy.Tag, ...]]] = set()', 'public_identities: dict[tuple[Any, str | None, tuple[legacy.Tag, ...]], str | None] = {}')
rep('            if public_identity in public_identities:\n                raise ContainerBuildError(', '            if public_identity in public_identities and public_identities[public_identity] != target.registration_id:\n                raise ContainerBuildError(')
rep('            public_identities.add(public_identity)\n', '''            if public_identity in public_identities:
                if _analysis_active():
                    _analysis_issue(ContainerBuildError("Duplicate exposure of the same component", code="boundary-expose-duplicate", path=(boundary.name,)))
                continue
            public_identities[public_identity] = target.registration_id
''')
# Architecture scan only in analyse.
start=s.index('    for area, layers in (',s.index('def _prepare_boundary_visibility')); end=s.index('    return blueprint',start)
s=s[:start]+'    if _analysis_active():\n'+textwrap.indent(s[start:end],'    ')+s[end:]
# Per-call forwarder shape remains emission; return/result proofs are analysis only.
start=s.index('        if inspect.isgeneratorfunction(member) or inspect.isasyncgenfunction(member):',s.index('def _per_call_methods')); end=s.index('        methods.append(',start)
block=s[start:end].replace('raise ContainerBuildError(', '_analysis_issue(ContainerBuildError(')
# Close the extra issue invocation for each former raise (all have closing line indent 12).
block=block.replace('            )\n','            ))\n')
s=s[:start]+'        if _analysis_active():\n'+textwrap.indent(block,'    ')+s[end:]
start=s.index('    if not methods:',s.index('def _per_call_methods')); end=s.index('    return tuple(methods)',start)
block=s[start:end].replace('if not methods:', 'if _analysis_active() and not methods:').replace('raise ContainerBuildError(', '_analysis_issue(ContainerBuildError(').replace('        )\n','        ))\n')
s=s[:start]+block+s[end:]
# Annotation-only warmup restrictions report while keeping ordered emitted targets.
rep('                if root.component.lifespan != "singleton" or root.component.kind is not ComponentKind.registration:\n                    raise _warmup_build_error("warmup-non-singleton-target", service, source, plan=declaration.name)', '                if _analysis_active() and root.component.lifespan != "singleton":\n                    _analysis_issue(_warmup_build_error("warmup-non-singleton-target", service, source, plan=declaration.name))')
rep('                if identity in seen:\n                    raise _warmup_build_error("warmup-duplicate-target", service, source, plan=declaration.name)', '                if _analysis_active() and identity in seen:\n                    _analysis_issue(_warmup_build_error("warmup-duplicate-target", service, source, plan=declaration.name))')
# Build has no success report. Temporary graph ownership is intentionally a task21/23 bridge.
rep('    build_report: BuildReport = field(default_factory=BuildReport)', '    build_report: AnalysisReport | None = None')
rep('build_report=replace(plan.build_report, _graph=None, _explanations=()),', 'build_report=None,')
# Single rule runner with explicit outcomes and no runtime replay.
start=s.index('def _run_validation_rules('); end=s.index('\ndef _build_error_code(',start)
s=s[:start]+'''def _run_validation_rules(
    graph: CompiledGraph, definitions: Iterable[_ValidationRuleDefinition],
    profile: CompilationProfiler | None = None, *, budget_state: _BudgetState | None = None,
) -> tuple[BuildIssue, ...]:
    state = _ANALYSIS_STATE.get()
    if state is None:
        raise RuntimeError("Validation rules require an active analysis")
    issues: list[BuildIssue] = []
    contexts: dict[str | None, ValidationContext] = {}
    for index, definition in enumerate(definitions):
        boundary = definition.origin.boundary
        outcome = "completed"
        rule_issues: list[BuildIssue] = []
        try:
            if budget_state is not None:
                budget_state.admit("preparation_operations", "analysis rules", origin=definition.origin)
            context = contexts.get(boundary)
            if context is None:
                visible_graph = graph
                if boundary is not None:
                    visible_graph = replace(graph,
                        roots=tuple(root for root in graph.roots if root.area == boundary),
                        entrypoints=tuple(root for root in graph.entrypoints if root.area == boundary),
                        _manifest_cache={}, _ownership_report_cache=[], _occurrence_paths_cache={},
                        _component_membership_cache=[], _analysis_index_cache=None)
                context = ValidationContext(visible_graph, boundary=boundary)
                contexts[boundary] = context
            if profile is not None:
                profile.count("analysis validation rule calls")
            result = definition.rule(context)
            if inspect.isawaitable(result) or inspect.isasyncgen(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise TypeError("Validation rules must return a synchronous iterable")
            iterator = iter(result)
            while True:
                if budget_state is not None:
                    budget_state.admit("preparation_operations", "analysis rules", origin=definition.origin)
                try:
                    issue = next(iterator)
                except StopIteration:
                    break
                if not _valid_build_issue(issue):
                    raise TypeError("Validation rule yielded a malformed BuildIssue")
                rule_issues.append(_located_rule_issue(issue, context, definition.origin))
        except _BudgetStop:
            outcome = "interrupted"
            raise
        except MemoryError:
            raise
        except Exception as error:
            outcome = "failed"
            rule_issues.append(BuildIssue("validation-rule-error", IssueSeverity.error,
                f"Validation rule {qualified_name(definition.rule)} failed: {type(error).__name__}: {error}",
                _origin=definition.origin))
        finally:
            issues.extend(rule_issues)
            state.issues.extend(rule_issues)
            state.rule_outcomes.append(AnalysisRuleOutcome(
                f"rule:{index + 1}", qualified_name(definition.rule), definition.origin.layer,
                boundary, boundary, outcome, tuple(rule_issues)))
    return tuple(issues)

'''+s[end:]
# Finalizer executes only analysis audits; execution bridge merely wraps existing roots.
rep('    all_roots = _graph_roots(plan)\n    entrypoints:', '''    all_roots = _graph_roots(plan)
    if not _analysis_active():
        # Temporary support for warmup/observation until tasks21/23 replace these readers.
        return replace(plan, compiled_graph=CompiledGraph(roots=all_roots, build_args=plan.build_args))
    entrypoints:''')
start=s.index('    validation_runner = (',s.index('def _finalize_plan')); end=s.index('    return replace(\n        plan,\n        compiled_graph=compiled_graph,',start)
s=s[:start]+'''    state = cast(_AnalysisState, _ANALYSIS_STATE.get())
    state.graph = compiled_graph
    deduplicated = tuple(dict.fromkeys((*state.issues, *built_in_issues)))
    report = AnalysisReport(deduplicated, checked_roots=len(all_roots), _graph=compiled_graph,
        _evidence=tuple(_issue_failure_evidence(issue) if issue._origin is not None else None for issue in deduplicated))
'''+s[end:]
# The completed report is sealed AFTER warmup binding; all rules see full available graph.
rep('        retained = _prune_orphan_registrations(finalized) if clean_orphans else finalized', '''        analysis = _ANALYSIS_STATE.get()
        if analysis is not None:
            analysis.plan = finalized
            analysis.graph = finalized.compiled_graph
            _run_validation_rules(cast(CompiledGraph, finalized.compiled_graph), blueprint.validation_rules,
                                  profile, budget_state=budget_state)
            issues = tuple(dict.fromkeys((*cast(AnalysisReport, finalized.build_report).issues, *analysis.issues)))
            complete = all(outcome.status == "completed" for outcome in analysis.rule_outcomes)
            finalized = replace(finalized, build_report=replace(cast(AnalysisReport, finalized.build_report),
                issues=issues, complete=complete, rule_outcomes=tuple(analysis.rule_outcomes),
                stage_outcomes=(AnalysisStageOutcome("declarations", "completed"),
                                AnalysisStageOutcome("wiring", "completed"),
                                AnalysisStageOutcome("built-in checks", "completed")),
                requested_roots=len(_graph_roots(finalized)), compiled_roots=len(_graph_roots(finalized))))
            analysis.plan = finalized
        retained = _prune_orphan_registrations(finalized) if clean_orphans else finalized''')
# Alias audit and template stability proofs run only for analyse and cannot abort valid emission.
start=s.index('    alias_errors = (',s.index('def _compile_with_report')); end=s.index('    try:\n        if any(layer.registration_templates',start)
s=s[:start]+'''    entry_points = _declared_entry_point_labels(blueprint) if _analysis_active() else ()
    analysis = _ANALYSIS_STATE.get()
    if analysis is not None:
        analysis.definitions = blueprint.validation_rules
        for error in _blueprint_alias_errors(blueprint):
            analysis.issues.extend(_alias_error_report((error,)).issues)
'''+s[end:]
rep('        _check_registration_template_sources(blueprint)', '        _analyse_check(_check_registration_template_sources, blueprint)')
rep('        if expansion.candidates:\n', '        if expansion.candidates and _analysis_active():\n')
# Make checking return the original emitted visibility even after an audit finding.
rep('''    if changed or missing:
        raise ContainerBuildError(''', '''    if changed or missing:
        _analysis_issue(ContainerBuildError(''')
rep('''            path=(*changed, *missing, *provenance),
        )''','''            path=(*changed, *missing, *provenance),
        ))''')
# No build diagnostic retries/report wrappers, including failures during preparation.
rep('    except TypeAliasNormalizationError as error:\n        report = _alias_error_report((error,))', '''    except TypeAliasNormalizationError as error:
        if not _analysis_active():
            raise ContainerBuildError("Type alias cannot be bound", code=error.code, path=(alias_label(error.alias),)) from None
        report = _alias_error_report((error,))''')
# Find preparation catch specifically.
idx=s.index('    except ContainerBuildError as error:\n        issue = BuildIssue(',s.index('def _compile_with_report'))
s=s[:idx]+s[idx:].replace('    except ContainerBuildError as error:\n        issue = BuildIssue(', '    except ContainerBuildError as error:\n        if not _analysis_active():\n            raise\n        issue = BuildIssue(',1)
idx=s.index('    except Exception as error:\n        if compiled is not None',s.index('def _compile_with_report'))
s=s[:idx]+s[idx:].replace('    except Exception as error:\n        if compiled is not None', '''    except MemoryError:
        raise
    except Exception as error:
        if not _analysis_active():
            if isinstance(error, ContainerBuildError):
                raise ContainerBuildError(_safe_error_message(error), code=error.code, path=error.path) from None
            raise
        if compiled is not None''',1)
# Remove automatic rich capture and all deferred-rule retention.
rep('        conservative_rules: bool = False,\n','',99)
rep('        inspection_lifetime = _InspectionLifetime() if conservative_rules and not explain_metadata else None','        inspection_lifetime = None')
start=s.index('            # Legacy build rules may consume rich graph evidence.'); end=s.index('            inputs["explain_metadata"]',start)
s=s[:start]+'            inputs["diagnostics"] = diagnostics\n'+s[end:]
start=s.index('                validation_rules=tuple('); end=s.index('                _blueprint=',start)
s=s[:start]+'                validation_rules=(),\n'+s[end:]
rep('                conservative_rules,\n','',99)
# Pre-admission parsing and a single admitted compilation attempt; reference release follows task21.
rep('        self._built = False\n','        self._built = False\n        self._compiling = False\n')
rep('        if self._built:\n            raise BuilderAlreadyBuiltError("Builders are single-use after a successful build")','        if self._built or self._compiling:\n            raise BuilderAlreadyBuiltError("Builders are consumed by one admitted compilation attempt")')
start=s.index('    def _build_plan('); pos=s.index('        if budget is not None',start)
s=s[:pos]+'''        self._assert_mutable()
        if profile is not None and not isinstance(profile, CompilationProfiler):
            raise TypeError("profile must be a CompilationProfiler instance or None")
        build_args = self._effective_build_args(build_args)
        parent = getattr(self, "_parent", None)
        if parent is not None:
            parent._ensure_open()
'''+s[pos:]
rep('        completed = False\n        try:\n', '        completed = False\n        self._compiling = True\n        try:\n')
rep('''        finally:
            _BUILD_INSPECTION_LIFETIME.reset(inspection_token)''','''        finally:
            self._compiling = False
            self._built = True
            _BUILD_INSPECTION_LIFETIME.reset(inspection_token)''')
rep('''        self._assert_mutable()
        parent = getattr(self, "_parent", None)
        if parent is not None:
            parent._ensure_open()
        inputs: _CompilationInputs''','''        parent = getattr(self, "_parent", None)
        if parent is not None:
            parent._ensure_open()
        inputs: _CompilationInputs''')
rep('''    def _snapshot(self, budget_state: _BudgetState | None = None) -> _BoundaryBlueprint:
        self._assert_mutable()''','''    def _snapshot(self, budget_state: _BudgetState | None = None) -> _BoundaryBlueprint:''')
# Public operations, no mode argument. Private harness remains only for historical probes.
start=s.index('BuildMode = Literal["run", "analysis"]'); end=s.index('class ContainerBuilder(',start)
s=s[:start]+s[end:]
for cls in ['ContainerBuilder','ScopeBuilder']:
    start=s.index('    def build(',s.index('class '+cls+'(')); end=s.index('    def _build(',start)
    ret='Container' if cls=='ContainerBuilder' else 'Scope'
    s=s[:start]+f'''    def build(
        self, *, build_args: Mapping[str, Any] | None = None,
        profile: CompilationProfiler | None = None, budget: CompilationBudget | None = None,
        instrumentation: Instrumentation | None = None,
    ) -> {ret}:
        """Emit execution instructions without running validation or policy audits."""
        return self._build(build_args=build_args, profile=profile, budget=budget,
            instrumentation=instrumentation, clean_orphans=True, diagnostics=False,
            explain_metadata=False, provider_roots=self._declared_provider_roots,
            allow_scope_builders=False, check_unreachable=False, aggregate_errors=False)

    def analyse(
        self, *, build_args: Mapping[str, Any] | None = None,
        profile: CompilationProfiler | None = None, budget: CompilationBudget | None = None,
    ) -> AnalysisResult[{ret}]:
        """Complete supported analysis and all available rules without activation."""
        return self._analyse(build_args=build_args, profile=profile, budget=budget)

'''+s[end:]
rep('def build_mode(self) -> BuildMode:', 'def build_mode(self) -> Literal["run", "analysis"]:')
rep('"""Private compiler policy harness; public callers must use build(mode=...)."""','"""Private historical compiler harness; public callers use build() or analyse()."""',99)
# No report access can cause rule replay, including transitional runtime readers.
start=s.index('    def validation_report(self) -> BuildReport:'); end=s.index('    @property\n    def build_args',start)
s=s[:start]+'''    def validation_report(self) -> AnalysisReport:
        """Read already captured findings; use analyse() to perform validation."""
        if self._plan.build_report is None:
            raise RuntimeError("Execution runtimes have no analysis report; use a fresh builder.analyse()")
        return self._plan.build_report

'''+s[end:]
# Snapshot shapes remain compatible with task21 finalization; result owns report/test runtimes.
start=s.index('    def _effective_build_args(',s.index('class _BuilderBase'))
s=s[:start]+'''    def _analyse(self, *, build_args=None, profile=None, budget=None):
        self._assert_mutable()
        if profile is not None and not isinstance(profile, CompilationProfiler):
            raise TypeError("profile must be a CompilationProfiler instance or None")
        state = _AnalysisState()
        token = _ANALYSIS_STATE.set(state)
        if profile is not None:
            profile._begin()
        profile_state = "interrupted"
        try:
            plan = self._build_plan(build_args, profile, False, budget, True, True,
                                    self._declared_provider_roots, True, True, True)
            result = AnalysisResult(cast(AnalysisReport, plan.build_report), plan.compiled_graph,
                                    None, plan, self._owner_token, getattr(self, "_parent", None))
            profile_state = "completed"
            return result
        except ContainerBuildError as error:
            prior = error.report or AnalysisReport((BuildIssue(error.code or "compile-error", IssueSeverity.error,
                _safe_error_message(error), path=error.path),))
            outcomes = list(state.rule_outcomes)
            status = "interrupted" if any(issue.code == "compilation-budget-exceeded" for issue in prior.issues) else "unavailable"
            for index, definition in enumerate(state.definitions[len(outcomes):], start=len(outcomes) + 1):
                outcomes.append(AnalysisRuleOutcome(f"rule:{index}", qualified_name(definition.rule),
                    definition.origin.layer, definition.origin.boundary, definition.origin.boundary,
                    status, ()))
            issues = tuple(dict.fromkeys((*state.issues, *prior.issues)))
            report = replace(prior, issues=issues, complete=False, rule_outcomes=tuple(outcomes),
                stage_outcomes=(AnalysisStageOutcome("declarations", "partial"),
                                AnalysisStageOutcome("wiring", "failed"),
                                AnalysisStageOutcome("full graph checks", "unavailable")))
            profile_state = "failed"
            return AnalysisResult(report, state.graph, error.partial_graph, None,
                                  self._owner_token, getattr(self, "_parent", None))
        finally:
            _ANALYSIS_STATE.reset(token)
            if profile is not None:
                profile._finish(profile_state)

'''+s[start:]
# Minimal result ownership plumbing; richer reference release/composition work belongs to tasks21–23.
start=s.index('class ContainerBuilder(')
s=s[:start]+'''TRuntime = TypeVar("TRuntime", bound=Scope)


class AnalysisRuntimeUnavailableError(RuntimeError):
    def __init__(self, report: AnalysisReport):
        self.report = report
        super().__init__("This analysis has no complete execution plan")


class AnalysisResult(typing.Generic[TRuntime]):
    """Completed analysis facts and an optional emitted plan for explicit tests."""
    def __init__(self, report, graph, partial_graph, plan, owner_token, parent):
        self.report = report
        self.graph = graph
        self.partial_graph = partial_graph
        self._plan = plan
        self._owner_token = owner_token
        self._parent = parent
        self._runtimes: list[Scope] = []
        self._closed = False
        # External immutable composition ownership is implemented by task23.
        self.composition = None

    @property
    def emission_complete(self) -> bool:
        return self._plan is not None

    @property
    def selected_registrations(self) -> tuple[RegistrationInfo, ...] | None:
        return None if self._plan is None else self._plan.selected_registrations

    def create_runtime(self, *, instrumentation: Instrumentation | None = None) -> TRuntime:
        if self._closed:
            raise RuntimeError("Analysis result is closed")
        if self._plan is None:
            raise AnalysisRuntimeUnavailableError(self.report)
        if instrumentation is not None and not isinstance(instrumentation, Instrumentation):
            raise TypeError("instrumentation must be an Instrumentation instance or None")
        plan = self._plan
        if self._parent is not None:
            self._parent._ensure_open()
        if instrumentation is not None:
            plan, fingerprint, labels, paths = _observe_plan(plan, instrumentation, self._owner_token, self._parent)
        # Do not reduce the graph in place: the result still owns its captured facts.
        # Execution-only projection and independent preconfiguration state are task21 work.
        plan = replace(plan, build_report=None, validation_rules=())
        if self._parent is None:
            runtime = (_ObservedContainer if instrumentation is not None else Container)(plan, self._owner_token)
        else:
            runtime = (_ObservedScope if instrumentation is not None else Scope)(plan,
                container=self._parent.container, parent=self._parent, owners=self._parent._owners,
                owned_token=self._owner_token, inherit_scoped=False)
        if instrumentation is not None:
            runtime._install_observation(instrumentation.profiler, fingerprint, labels, paths)
        self._runtimes.append(runtime)
        return cast(TRuntime, runtime)

    def close(self) -> None:
        self._closed = True
        errors = []
        for runtime in reversed(self._runtimes):
            try:
                runtime.__exit__(None, None, None)
            except Exception as error:
                errors.append(error)
        self._runtimes.clear()
        if errors:
            raise ExceptionGroup("Analysis test runtime cleanup failed", errors)

    async def aclose(self) -> None:
        self._closed = True
        errors = []
        for runtime in reversed(self._runtimes):
            try:
                await runtime.__aexit__(None, None, None)
            except Exception as error:
                errors.append(error)
        self._runtimes.clear()
        if errors:
            raise ExceptionGroup("Analysis test runtime cleanup failed", errors)

    def __enter__(self):
        if self._closed:
            raise RuntimeError("Analysis result is closed")
        return self

    def __exit__(self, *args):
        self.close()

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, *args):
        await self.aclose()


'''+s[start:]
ast.parse(s)
P.write_text(s)
# Shared completed report type; alias allows task24 migration to happen coherently later.
p=Path('clean_ioc/tooling.py'); t=p.read_text(); t=t.replace('class BuildReport:', 'class AnalysisReport:',1)
anchor='@dataclass(frozen=True, slots=True)\nclass AnalysisReport:'
t=t.replace(anchor,'''@dataclass(frozen=True, slots=True)
class AnalysisRuleOutcome:
    declaration: str
    rule: str
    layer: str | None
    boundary: str | None
    context: str | None
    status: str
    issues: tuple[BuildIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"declaration": self.declaration, "rule": self.rule, "layer": self.layer,
                "boundary": self.boundary, "context": self.context, "status": self.status,
                "issues": [issue.to_dict() for issue in self.issues]}


@dataclass(frozen=True, slots=True)
class AnalysisStageOutcome:
    stage: str
    status: str
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"stage": self.stage, "status": self.status, "detail": self.detail}


'''+anchor)
t=t.replace('    checked_roots: int = 0\n', '''    checked_roots: int = 0
    complete: bool = field(default=True, kw_only=True)
    requested_roots: int = field(default=0, kw_only=True)
    compiled_roots: int = field(default=0, kw_only=True)
    failed_roots: int = field(default=0, kw_only=True)
    rule_outcomes: tuple[AnalysisRuleOutcome, ...] = field(default=(), kw_only=True)
    stage_outcomes: tuple[AnalysisStageOutcome, ...] = field(default=(), kw_only=True)
''',1)
t=t.replace('        return not self.errors\n', '        return self.complete and not self.errors\n',1)
t=t.replace('            "checked_roots": self.checked_roots,\n', '''            "checked_roots": self.checked_roots,
            "complete": self.complete,
            "requested_roots": self.requested_roots,
            "compiled_roots": self.compiled_roots,
            "failed_roots": self.failed_roots,
            "rule_outcomes": [outcome.to_dict() for outcome in self.rule_outcomes],
            "stage_outcomes": [outcome.to_dict() for outcome in self.stage_outcomes],
''',1)
t=t.replace('''        else:
            count = len(self.errors)
            noun = "error" if count == 1 else "errors"
            heading = f"Container build failed with {count} {noun}."''','''        else:
            count = len(self.errors)
            noun = "error" if count == 1 else "errors"
            heading = f"Analysis {'incomplete' if not self.complete else 'invalid'} with {count} {noun}."''',1)
t=t.replace('@dataclass(frozen=True, slots=True)\nclass FailureEvidence:', 'BuildReport = AnalysisReport  # Transitional import spelling; removal/migration belongs to task24.\n\n\n@dataclass(frozen=True, slots=True)\nclass FailureEvidence:',1)
p.write_text(t)
p=Path('clean_ioc/components.py'); t=p.read_text().replace('ValidationRuleMode: TypeAlias = Literal["build", "validation"]\n','').replace('def add_validation_rule(self, rule: ValidationRule, *, mode: ValidationRuleMode = "build") -> None:', 'def add_validation_rule(self, rule: ValidationRule) -> None:'); p.write_text(t)
p=Path('clean_ioc/policies.py'); t=p.read_text().replace('ValidationRule | tuple[ValidationRule, ValidationRuleMode]','ValidationRule').replace(', ValidationRuleMode',''); start=t.index('def _validate_mode('); end=t.index('def _compiled_decorator_type',start); t=t[:start]+t[end:]; start=t.index('    """Install a frozen list of rules,'); end=t.index('\n\n@dataclass(frozen=True, slots=True)\nclass Layer',start)
t=t[:start]+'''    """Install one ordered set of rules evaluated only during analyse()."""
    name: str
    rules: tuple[ValidationRule, ...]

    def __init__(self, name: str, rules: Iterable[PolicyPackEntry]) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("A policy pack requires a nonempty name")
        entries = tuple(rules)
        for rule in entries:
            _validate_callback(rule)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "rules", entries)

    def __call__(self, builder: ComponentBuilder) -> None:
        for rule in self.rules:
            builder.add_validation_rule(_packed_rule(self.name, rule))
'''+t[end:]; p.write_text(t)
p=Path('clean_ioc/__init__.py'); t=p.read_text().replace('    ValidationRuleMode,\n','').replace('    BuildMode,\n','').replace('    "ValidationRuleMode",\n','').replace('    "BuildMode",\n',''); t=t.replace('from .container import (','from .container import (\n    AnalysisResult,\n    AnalysisRuntimeUnavailableError,'); t=t.replace('from .tooling import (','from .tooling import (\n    AnalysisReport,\n    AnalysisRuleOutcome,\n    AnalysisStageOutcome,'); t=t.replace('__all__ = [','__all__ = [\n    "AnalysisResult",\n    "AnalysisRuntimeUnavailableError",\n    "AnalysisReport",\n    "AnalysisRuleOutcome",\n    "AnalysisStageOutcome",'); p.write_text(t)
