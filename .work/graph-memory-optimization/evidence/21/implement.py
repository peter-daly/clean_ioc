from pathlib import Path
p=Path('clean_ioc/container.py'); s=p.read_text()
# Distinct runtime owner: no diagnostic or declaration storage.
a=s.index('@dataclass(frozen=True, slots=True)\nclass _PlanSet:'); b=s.index('\n\n@dataclass(frozen=True, slots=True)\nclass _GraphExplanationSidecars:',a)
old=s[a:b]
exec_fields='''@dataclass(frozen=True, slots=True)
class _ExecutionPlan:
    graph: _ComponentGraph
    roots: dict[Any, tuple[_RootPlan, ...]]
    default_roots: dict[Any, _RootPlan]
    default_root_groups: dict[Any, tuple[_RootPlan, ...]]
    build_args: Mapping[str, Any]
    provider_roots: Mapping[Any, tuple[_RootPlan, ...]] = field(default_factory=dict)
    managed_provider_roots: Mapping[Any, tuple[_RootPlan, ...]] = field(default_factory=dict)
    warmup_steps: Mapping[str, tuple[_RootPlan, ...]] = field(default_factory=lambda: types.MappingProxyType({}))
    warmup_infos: tuple[WarmupPlanInfo, ...] = ()
    warmup_fingerprint: str = ""
    selected_registrations: tuple[RegistrationInfo, ...] = ()
    slots: frozenset[tuple[Any, str | None]] = frozenset()
    ensured_import_modules: tuple[str, ...] = ()
    identity: str = field(default_factory=lambda: str(uuid4()))


'''
base_names=['graph','roots','default_roots','default_root_groups','build_args','provider_roots','managed_provider_roots','warmup_steps','warmup_infos','warmup_fingerprint','selected_registrations','slots','ensured_import_modules']
lines=old.replace('class _PlanSet:','class _PlanSet(_ExecutionPlan):').splitlines()
lines=[line for line in lines if not any(line.startswith('    '+name+':') for name in base_names)]
lines=[line.replace('    _blueprint: _Blueprint | None','    _blueprint: _Blueprint | None = None') for line in lines]
s=s[:a]+exec_fields+'\n'.join(lines)+s[b:]
s=s.replace('    plan: _PlanSet | None = None\n','    plan: _ExecutionPlan | None = None\n',1)
# Root emission shared by runtime and analysis. Architecture compilation begins afterwards.
a=s.index('    def compile(\n',s.index('class _Compiler:')); b=s.index('        if service_types is None and area is None and include_boundaries:',a)
head=s[a:b]
body=head[head.index('        if self._source_inspection:'):]
body=body.replace('        architecture_roots: list[tuple[str | None, Any, _RootPlan]] = []\n','')
body=body.replace('            architecture_roots.extend((area, service_type, plan) for plan in roots[service_type])\n','').replace('            architecture_roots.extend((area, entrypoint.service_type, plan) for plan in plans)\n','')
root_method='''    def compile_execution(self) -> _ExecutionPlan:
        plan, _ = self._compile_execution_roots()
        return plan

    def _compile_execution_roots(
        self, service_types: Iterable[Any] | None = None, *, area: str | None = None
    ) -> tuple[_ExecutionPlan, dict[str, dict[Any, tuple[_CandidateRecord, ...]]]]:
'''+body+'''        default_root_groups = {
            service_type: _preferred_root_plans(plan for plan in plans if plan.component.name is None)
            for service_type, plans in roots.items()
        }
        return _ExecutionPlan(
            graph=self.graph,
            roots=roots,
            default_roots={service_type: plans[0] for service_type, plans in default_root_groups.items() if plans},
            default_root_groups=default_root_groups,
            build_args=self.build_args,
            provider_roots=types.MappingProxyType(provider_roots),
            managed_provider_roots=types.MappingProxyType(dict(self._managed_provider_roots)),
            slots=self.blueprint.slots,
            ensured_import_modules=tuple(dict.fromkeys(
                name for layer in (*self.blueprint.layers, *(b.layer for b in self.blueprint.boundaries))
                for name in layer.ensured_import_modules
            )),
        ), area_records

    def compile(
        self,
        service_types: Iterable[Any] | None = None,
        *,
        area: str | None = None,
        include_boundaries: bool = True,
        clean_orphans: bool = True,
    ) -> _PlanSet:
        execution, area_records = self._compile_execution_roots(service_types, area=area)
        roots = execution.roots
        provider_roots = execution.provider_roots
        architecture_roots = [(area, service, root) for service, plans in roots.items() for root in plans]
        analysis = _ANALYSIS_STATE.get()
        if analysis is not None and service_types is None and area is None:
            execution = _compile_warmup_plans(execution, self._budget, blueprint=self.blueprint)
            # Capture the primary emitted plan before inspection-only roots can fail.
            # The detached graph also prevents later inspection mutations leaking in.
            analysis.plan = _project_execution_plan(execution, clone_graph=True)
'''
s=s[:a]+root_method+s[b:]
# rich plan includes already-bound startup instructions, no replay
needle='''            graph=self.graph,
            diagnostics=self._diagnostics,'''
s=s.replace(needle,'''            graph=self.graph,
            warmup_steps=execution.warmup_steps,
            warmup_infos=execution.warmup_infos,
            warmup_fingerprint=execution.warmup_fingerprint,
            identity=execution.identity,
            diagnostics=self._diagnostics,''',1)
# finalizer now analysis-only (historical private harness gets rich output but not runtime path)
s=s.replace('''    if not _analysis_active():
        # Temporary support for warmup/observation until tasks21/23 replace these readers.
        return replace(plan, compiled_graph=CompiledGraph(roots=all_roots, build_args=plan.build_args))
''','')
# Minimal warmup binding; future task23 observation/catalog compatibility work remains.
s=s.replace('''def _compile_warmup_plans(plan: _PlanSet, budget_state: _BudgetState | None = None) -> _PlanSet:
    if not any(layer.warmup_declarations for layer in plan.blueprint.layers):
        return plan
    graph = cast(CompiledGraph, plan.compiled_graph)
    paths = {component.occurrence_id: path for path, component in graph._component_paths(all_roots=True).items()}
''','''def _compile_warmup_plans(
    plan: _ExecutionPlan, budget_state: _BudgetState | None = None, *, blueprint: _Blueprint
) -> _ExecutionPlan:
    if not any(layer.warmup_declarations for layer in blueprint.layers):
        return plan
''')
a=s.index('def _compile_warmup_plans(');b=s.index('\n\ndef _declared_entry_point_labels',a)
w=s[a:b].replace('plan.blueprint','blueprint').replace('paths[root.component.occurrence_id]','f"component:{root.component.occurrence_id}"').replace('        compiled_graph=replace(graph, warmup_plans=tuple(infos)),\n','').replace('warmup_fingerprint=graph.manifest(all_roots=True).fingerprint','warmup_fingerprint=plan.identity')
s=s[:a]+w+s[b:]
# Extract shared preparation from the rich orchestration.
a=s.index('def _compile_with_report('); b=s.index('    compiler = _Compiler(',a)
prep=s[a:b]; sig=prep[:prep.index('    compilation_inputs:')]
prep_body=prep[prep.index('    compilation_inputs:'):]
prep_sig=sig.replace('def _compile_with_report(','def _prepare_compilation(').replace(') -> _PlanSet:',') -> tuple[_Blueprint, _CompilationInputs]:')
s=s[:a]+prep_sig+prep_body+'    return blueprint, compilation_inputs\n\n\n'+sig+'''    blueprint, compilation_inputs = _prepare_compilation(
        blueprint, build_args=build_args,
        anchored_singleton_steps=anchored_singleton_steps,
        anchored_pre_configuration_steps=anchored_pre_configuration_steps,
        anchored_owner_tokens=anchored_owner_tokens, inherited_graph_sidecars=inherited_graph_sidecars,
        profile=profile, budget_state=budget_state, diagnostics=diagnostics,
        explain_metadata=explain_metadata, provider_roots=provider_roots,
    )
    entry_points = _declared_entry_point_labels(blueprint) if _analysis_active() else ()
'''+s[b:]
# Already-bound warmups on analysis plan.
a=s.index('        finalized = _compile_warmup_plans(',s.index('def _compile_with_report(')); b=s.index('        analysis = _ANALYSIS_STATE.get()',a)
s=s[:a]+'''        finalized = _finalize_plan(
            plan, profile, budget_state, check_unreachable=check_unreachable,
            inspection_lifetime=inspection_lifetime,
        )
        if finalized.compiled_graph is not None and finalized.warmup_infos:
            finalized = replace(finalized, compiled_graph=replace(
                finalized.compiled_graph, warmup_plans=finalized.warmup_infos
            ))
'''+s[b:]
a=s.index('            analysis.plan = replace(',a);b=s.index('            analysis.graph =',a)
s=s[:a]+s[b:]
s=s.replace('            analysis.plan = finalized\n','',1)
p.write_text(s)
