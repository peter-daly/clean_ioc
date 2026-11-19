from pathlib import Path
p=Path('clean_ioc/container.py');s=p.read_text()
for name in ('_release_execution_composition','_retain_runtime_graph','_selected_registration_catalogue'):
 s=s.replace(f'def {name}(plan: _PlanSet',f'def {name}(plan: _ExecutionPlan')
s=s.replace('plan.architecture_roots if plan._blueprint is not None else ()','plan.architecture_roots if isinstance(plan, _PlanSet) and plan._blueprint is not None else ()')
s=s.replace('architecture = plan.architecture_roots if include_architecture or plan._blueprint is not None else ()','architecture = (plan.architecture_roots if isinstance(plan, _PlanSet) and (include_architecture or plan._blueprint is not None) else ())')
insert=s.index('\ndef _reduce_explanation_metadata(')
s=s[:insert]+'''
def _project_execution_plan(plan: _ExecutionPlan, *, clone_graph: bool = False) -> _ExecutionPlan:
    """Copy library-owned executable carriers, preserving all opaque application values.

    Only this plan's graph and preconfiguration state are projected. Parent graphs
    and their singleton/preconfiguration steps remain the actual borrowed anchors.
    """
    graph = plan.graph
    if clone_graph:
        graph = _ComponentGraph()
        graph._views = list(plan.graph._views)
        if plan.graph._records is None:
            graph._drafts = dict(plan.graph._drafts)
        else:
            graph._records = dict(plan.graph._records)
    memo: dict[int, Any] = {}
    states: dict[int, _PreConfigurationState] = {}
    executable = (_RootPlan, _Step, _CompiledDependency, _CompiledDecorator,
                  _CompiledPreConfiguration, _CompiledResolutionRequest)

    def project(value: Any) -> Any:
        if isinstance(value, Component):
            return Component(graph, value.occurrence_id) if value._graph is plan.graph else value
        if isinstance(value, (_RegistrationStep, _CompiledPreConfiguration)) and value.component._graph is not plan.graph:
            return value
        identity = id(value)
        if identity in memo:
            return memo[identity]
        if isinstance(value, executable):
            result = replace(value)
            memo[identity] = result
            for item in fields(value):
                if isinstance(value, _ValueStep) and item.name == "value":
                    continue
                original = getattr(value, item.name)
                if isinstance(value, _CompiledPreConfiguration) and item.name == "state":
                    replacement = states.get(id(original))
                    if replacement is None:
                        replacement = states[id(original)] = _PreConfigurationState()
                else:
                    replacement = project(original)
                object.__setattr__(result, item.name, replacement)
            return result
        if type(value) is tuple:
            result = tuple(project(item) for item in value)
            memo[identity] = result
            return result
        if type(value) in (dict, types.MappingProxyType):
            result = {key: project(item) for key, item in value.items()}
            memo[identity] = result
            return result
        return value

    projected = _ExecutionPlan(**{
        item.name: graph if item.name == "graph" else project(getattr(plan, item.name))
        for item in fields(_ExecutionPlan)
    })
    # Do not rebuild caller-owned build arguments or discovery metadata.
    projected = replace(projected, build_args=plan.build_args, selected_registrations=plan.selected_registrations)
    if clone_graph:
        _retain_runtime_graph(projected)
    _release_execution_composition(projected)
    if not projected.selected_registrations:
        projected = replace(projected, selected_registrations=_selected_registration_catalogue(projected))
    return projected


def _finalize_execution(plan: _ExecutionPlan) -> _ExecutionPlan:
    selected = _selected_registration_catalogue(plan)
    _retain_runtime_graph(plan)
    _release_execution_composition(plan)
    return replace(plan, selected_registrations=selected)

''' +s[insert:]
# Explicit execution orchestration, no rich failure adaptation.
insert=s.index('\ndef _compile_with_report(')
s=s[:insert]+'''
def _compile_execution(
    blueprint: _Blueprint,
    *,
    profile: CompilationProfiler | None = None,
    build_args: Mapping[str, Any] = _EMPTY_BUILD_ARGS,
    budget_state: _BudgetState | None = None,
    anchored_singleton_steps: dict[tuple[str, tuple[Any, ...]], _RegistrationStep] | None = None,
    anchored_pre_configuration_steps: dict[str, _CompiledPreConfiguration] | None = None,
    anchored_owner_tokens: frozenset[str] = frozenset(),
    inherited_graph_sidecars: Mapping[_ComponentGraph, _GraphExplanationSidecars] = types.MappingProxyType({}),
    provider_roots: tuple[Any, ...] | None = None,
) -> _ExecutionPlan:
    blueprint, _ = _prepare_compilation(
        blueprint, build_args=build_args, profile=profile, budget_state=budget_state,
        anchored_singleton_steps=anchored_singleton_steps,
        anchored_pre_configuration_steps=anchored_pre_configuration_steps,
        anchored_owner_tokens=anchored_owner_tokens, inherited_graph_sidecars=inherited_graph_sidecars,
        diagnostics=False, explain_metadata=False, provider_roots=provider_roots,
    )
    compiler = _Compiler(
        blueprint, build_args=build_args, profile=profile, budget_state=budget_state,
        anchored_singletons=anchored_singleton_steps,
        anchored_pre_configurations=anchored_pre_configuration_steps,
        anchored_owner_tokens=anchored_owner_tokens, inherited_graph_sidecars=inherited_graph_sidecars,
        diagnostics=False, explain_metadata=False, provider_roots=provider_roots,
    )
    try:
        plan = (compiler.compile_execution() if profile is None else profile.call(
            "primary compilation", "phase", compiler.compile_execution, attempt="primary"
        ))
        plan = _compile_warmup_plans(plan, budget_state, blueprint=blueprint)
        return (_finalize_execution(plan) if profile is None else profile.call(
            "runtime graph finalization", "graph freezing", _finalize_execution, plan
        ))
    except MemoryError:
        raise
    except Exception as error:
        if isinstance(error, ContainerBuildError):
            raise ContainerBuildError(_safe_error_message(error), code=error.code, path=error.path) from None
        if getattr(compiler, "_callback_failure_path", ()):
            raise ContainerBuildError(
                _safe_error_message(error), code="compile-error", path=compiler._callback_failure_path
            ) from None
        raise

''' +s[insert:]
# Public operations explicitly select the execution orchestrator, sharing admission only.
s=s.replace('''        aggregate_errors: bool,
    ) -> _PlanSet:
''','''        aggregate_errors: bool,
        *,
        operation: Callable[..., _ExecutionPlan] = _compile_with_report,
    ) -> _ExecutionPlan:
''',1)
needle='''            inputs["diagnostics"] = diagnostics
            inputs["explain_metadata"] = explain_metadata'''
s=s.replace(needle,'''            if operation is _compile_execution:
                inputs["provider_roots"] = requested_providers
                execution = operation(blueprint, profile=profile, **inputs)
                if state is not None:
                    state.check()
                completed = True
                return execution
            inputs["diagnostics"] = diagnostics
            inputs["explain_metadata"] = explain_metadata''',1)
# Release admitted declarations in finally, after wiring/freezing/analysis consumers.
s=s.replace('''            self._built = True
            _BUILD_INSPECTION_LIFETIME.reset(inspection_token)''','''            self._built = True
            self._release_declarations()
            _BUILD_INSPECTION_LIFETIME.reset(inspection_token)''',1)
insert=s.index('    def bundle_run_key(',s.index('class _BuilderBase:'))
s=s[:insert]+'''    def _release_declarations(self) -> None:
        """Drop only builder-owned containers after the single admitted attempt."""
        for boundary in self._boundaries:
            boundary._release_declarations()
            boundary._uses = ()
            boundary._exposes = ()
            boundary._built = True
        self._composition = cast(legacy.Container, None)
        for name in (
            "_registration_when", "_candidate_when", "_registration_preferences",
            "_registration_parent_precedence", "_registration_policies", "_root_policies",
            "_registration_origins", "_factory_ids", "_factory_specializations", "_provider_maps",
            "_contributions", "_service_groups", "_pattern_ids", "_fallback_ids", "_decorators",
            "_decorator_templates", "_registration_templates", "_removed_registration_template_ids",
            "_decorator_declaration_ids", "_removed_template_ids", "_instance_implementation_types",
            "_removed_decorator_ids", "_pre_configurations", "_pre_configuration_states",
            "_registration_discoveries", "_slots", "_slot_origins", "_entrypoints",
            "_warmup_declarations", "_validation_rules", "_boundaries",
        ):
            getattr(self, name).clear()
        self._declared_provider_roots = None
        if hasattr(self, "_composition_blueprint"):
            self._composition_blueprint = None

    def _build_execution(self, *, build_args=None, profile=None, budget=None, instrumentation=None):
        self._assert_mutable()
        if instrumentation is not None and not isinstance(instrumentation, Instrumentation):
            raise TypeError("instrumentation must be an Instrumentation instance or None")
        if profile is not None and not isinstance(profile, CompilationProfiler):
            raise TypeError("profile must be a CompilationProfiler instance or None")
        parent = getattr(self, "_parent", None)
        parent_profiler = None if parent is None else getattr(parent, "_profiler", None)
        if parent_profiler is not None and instrumentation is None:
            instrumentation = Instrumentation(parent_profiler)
        if parent is not None and (None if instrumentation is None else instrumentation.profiler) is not parent_profiler:
            raise ValueError("overlay instrumentation must match its parent runtime")
        if profile is not None:
            profile._begin()
        status = "interrupted"
        try:
            plan = self._build_plan(
                build_args, profile, True, budget, False, False, self._declared_provider_roots,
                False, False, False, operation=_compile_execution,
            )
            if instrumentation is not None:
                plan, fingerprint, labels, paths = _observe_execution_bridge(plan, instrumentation, self._owner_token, parent)
            if parent is None:
                runtime = (_ObservedContainer if instrumentation is not None else Container)(plan, self._owner_token)
            else:
                runtime = (_ObservedScope if instrumentation is not None else Scope)(
                    plan, container=parent.container, parent=parent, owners=parent._owners,
                    owned_token=self._owner_token, inherit_scoped=False,
                )
            if instrumentation is not None:
                cast(_ObservedScope, runtime)._install_observation(instrumentation.profiler, fingerprint, labels, paths)
            status = "completed"
            return runtime
        except Exception:
            status = "failed"
            raise
        finally:
            if profile is not None:
                profile._finish(status)

''' +s[insert:]
# Public build only (private historical harness unchanged).
for cls in ('ContainerBuilder','ScopeBuilder'):
 a=s.index('class '+cls+'(');a=s.index('            return self._build(',a); b=s.index('\n        finally:',a)
 s=s[:a]+'''            return self._build_execution(
                build_args=build_args, profile=profile, budget=budget, instrumentation=instrumentation,
            )'''+s[b:]
# Runtime inspections fail explicitly while obsolete entrypoints await task24 removal.
s=s.replace('return "analysis" if self._plan.explain_metadata else "run"','return "analysis" if isinstance(self._plan, _PlanSet) and self._plan.explain_metadata else "run"')
s=s.replace('return self._plan.explain_metadata','return isinstance(self._plan, _PlanSet) and self._plan.explain_metadata')
s=s.replace('if not self._plan.explain_metadata:','if not isinstance(self._plan, _PlanSet) or not self._plan.explain_metadata:')
s=s.replace('if self._plan.build_report is None:','if not isinstance(self._plan, _PlanSet) or self._plan.build_report is None:')
s=s.replace('if self._plan._blueprint is None:','if not isinstance(self._plan, _PlanSet) or self._plan._blueprint is None:')
s=s.replace('        plan: _PlanSet,\n        *,\n        container:', '        plan: _ExecutionPlan,\n        *,\n        container:')
s=s.replace('def __init__(self, plan: _PlanSet, root_owner_token: str):','def __init__(self, plan: _ExecutionPlan, root_owner_token: str):')
# Analysis owns rich source explicitly for task23's forthcoming Composition capture.
s=s.replace('''                plan.compiled_graph,
                None,
                plan,
''','''                plan.compiled_graph,
                None,
                state.plan,
''',1)
s=s.replace('''            plan = self._build_plan(
                build_args, profile, False, budget, True, True, self._declared_provider_roots, True, True, True
            )''','''            plan = cast(_PlanSet, self._build_plan(
                build_args, profile, False, budget, True, True, self._declared_provider_roots, True, True, True
            ))''',1)
s=s.replace('''            profile_state = "completed"
            return result
''','''            result._composition_blueprint = plan.blueprint
            profile_state = "completed"
            return result
''',1)
s=s.replace('''        plan = self._plan
        if self._parent is not None:''','''        plan = _project_execution_plan(self._plan)
        if self._parent is not None:''',1)
s=s.replace('''            plan, fingerprint, labels, paths = _observe_plan(plan, instrumentation, self._owner_token, self._parent)
        # Do not reduce the graph in place: the result still owns its captured facts.
        # Execution-only projection and independent preconfiguration state are task21 work.
        plan = replace(plan, build_report=None, validation_rules=())''','''            plan, fingerprint, labels, paths = _observe_execution_bridge(plan, instrumentation, self._owner_token, self._parent)''',1)
s=s.replace('''        self.composition = None
''','''        self.composition = None
        self._composition_blueprint: _Blueprint | None = None
''',1)
# Match established cleanup, including fatal errors and single-error identity.
s=s.replace('''        errors = []
        for runtime in reversed(self._runtimes):''','''        errors: list[BaseException] = []
        for runtime in reversed(self._runtimes):''')
s=s.replace('''            except Exception as error:
                errors.append(error)
        self._runtimes.clear()
        if errors:
            raise ExceptionGroup("Analysis test runtime cleanup failed", errors)''','''            except BaseException as error:
                errors.append(error)
        self._runtimes.clear()
        _RuntimeOwner._raise_cleanup_failures(errors)''')
# Private source seam for interim scope correctness, never stored on the runtime.
a=s.index('    def __init__(self, parent: Scope):',s.index('class ScopeBuilder')); b=s.index('    def build(',a)
s=s[:a]+'''    def __init__(self, parent: Scope):
        parent._ensure_open()
        if not isinstance(parent._plan, _PlanSet) or parent._plan._blueprint is None:
            raise RuntimeError("Scope overlays require an explicitly retained composition")
        self._initialize(parent, parent._plan.blueprint)

    def _initialize(self, parent: Scope, blueprint: _Blueprint) -> None:
        parent._ensure_open()
        super().__init__()
        self._parent = parent
        self._composition_blueprint = blueprint
        self._bundle_container_id = parent.container._owned_token

    @classmethod
    def _from_blueprint(cls, parent: Scope, blueprint: _Blueprint) -> ScopeBuilder:
        # Temporary task21 test seam; task23 replaces this with Composition matching.
        builder = cls.__new__(cls)
        builder._initialize(parent, blueprint)
        return builder

'''+s[b:]
s=s.replace('parent._plan.blueprint.validation_rules','self._composition_blueprint.validation_rules')
s=s.replace('parent._plan.blueprint.boundaries','self._composition_blueprint.boundaries')
s=s.replace('parent._plan.blueprint.layers','self._composition_blueprint.layers')
s=s.replace('parent._plan.blueprint.boundary(name)','self._composition_blueprint.boundary(name)')
# Sidecars are captured only when the parent actually has analysis data (historical harness).
s=s.replace('''            sidecars.setdefault(ancestor._plan.graph, _graph_explanation_sidecars(ancestor._plan))''','''            if isinstance(ancestor._plan, _PlanSet):
                sidecars.setdefault(ancestor._plan.graph, _graph_explanation_sidecars(ancestor._plan))''')
# Temporary observer adapter is explicit, isolated, and not retained by execution.
insert=s.index('\ndef _observe_plan_impl(')
s=s[:insert]+'''
def _observe_execution_bridge(
    plan: _ExecutionPlan, instrumentation: Instrumentation, binding_token: str, parent_scope: Scope | None = None
) -> tuple[_ExecutionPlan, str, dict[Any, str], dict[int, str]]:
    """Temporary graph-based observer adapter; task23 removes this allocation."""
    bridge = _PlanSet(**{item.name: getattr(plan, item.name) for item in fields(_ExecutionPlan)},
        compiled_graph=CompiledGraph(roots=tuple(
            GraphRoot(service, root.component)
            for groups in (plan.roots, plan.provider_roots, plan.managed_provider_roots, plan.warmup_steps)
            for service, roots in groups.items() for root in roots
        ), build_args=plan.build_args))
    observed, fingerprint, labels, paths = _observe_plan(bridge, instrumentation, binding_token, parent_scope)
    return (_ExecutionPlan(**{item.name: getattr(observed, item.name) for item in fields(_ExecutionPlan)}),
            fingerprint, labels, paths)

''' +s[insert:]
# Anchoring must see deferred, map, warmup and provider execution roots too.
s=s.replace('''    plan: _PlanSet,
) -> dict[tuple[str, tuple[Any, ...]], _RegistrationStep]:''','''    plan: _ExecutionPlan,
) -> dict[tuple[str, tuple[Any, ...]], _RegistrationStep]:''')
s=s.replace('def _anchored_pre_configurations(plan: _PlanSet)', 'def _anchored_pre_configurations(plan: _ExecutionPlan)')
s=s.replace('''    all_plans = tuple(root for _, _, root in plan.architecture_roots) or tuple(
        root for plans in plan.roots.values() for root in plans
    )''','''    all_plans = (
        tuple(root for _, _, root in plan.architecture_roots) if isinstance(plan, _PlanSet) and plan.architecture_roots
        else tuple(root for groups in (plan.roots, plan.provider_roots, plan.managed_provider_roots, plan.warmup_steps)
                   for plans in groups.values() for root in plans)
    )''')
p.write_text(s)
# Migrate checks to absence of rich owners and explicit analysis source input.
p=Path('tests/test_analysis_pipeline.py');s=p.read_text().replace('assert runtime._plan.build_report is None','assert not hasattr(runtime._plan, "build_report")').replace('assert runtime._plan.validation_rules == ()','assert not hasattr(runtime._plan, "validation_rules")').replace('ScopeBuilder(parent)', 'ScopeBuilder._from_blueprint(parent, parent_result._composition_blueprint)');p.write_text(s)
