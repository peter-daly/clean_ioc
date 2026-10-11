from pathlib import Path
p=Path('clean_ioc/container.py');s=p.read_text()
s=s.replace('''    projected = _ExecutionPlan(**{
        item.name: graph if item.name == "graph" else project(getattr(plan, item.name))
        for item in fields(_ExecutionPlan)
    })
    # Do not rebuild caller-owned build arguments or discovery metadata.
    projected = replace(projected, build_args=plan.build_args, selected_registrations=plan.selected_registrations)''','''    values: dict[str, Any] = {item.name: getattr(plan, item.name) for item in fields(_ExecutionPlan)}
    values["graph"] = graph
    for name in ("roots", "default_roots", "default_root_groups", "provider_roots", "managed_provider_roots", "warmup_steps"):
        values[name] = project(values[name])
    projected = _ExecutionPlan(**values)''')
s=s.replace('def _reduce_explanation_metadata(plan: _PlanSet) -> _PlanSet:', 'def _reduce_explanation_metadata(plan: _ExecutionPlan) -> _ExecutionPlan:')
s=s.replace('''    if plan.explain_metadata:
        return plan
    architecture =''','''    if not isinstance(plan, _PlanSet) or plan.explain_metadata:
        return plan
    architecture =''',1)
s=s.replace('return self._plan._blueprint is not None','return isinstance(self._plan, _PlanSet) and self._plan._blueprint is not None')
# Read declaration source explicitly on builders only.
s=s.replace('self._composition_blueprint.validation_rules','self._source_blueprint.validation_rules').replace('self._composition_blueprint.boundaries','self._source_blueprint.boundaries').replace('self._composition_blueprint.layers','self._source_blueprint.layers').replace('self._composition_blueprint.boundary(name)','self._source_blueprint.boundary(name)')
s=s.replace('parent._plan.blueprint.local_registrations','self._source_blueprint.local_registrations').replace('_registration_template_definitions(parent._plan.blueprint)','_registration_template_definitions(self._source_blueprint)').replace('_template_definitions(parent._plan.blueprint)','_template_definitions(self._source_blueprint)').replace('return parent._plan.blueprint.decorator_definition','return self._source_blueprint.decorator_definition')
insert=s.index('    def _release_declarations(')
s=s[:insert]+'''    @property
    def _source_blueprint(self) -> _Blueprint:
        blueprint = getattr(self, "_composition_blueprint", None)
        if blueprint is None:
            raise RuntimeError("No retained composition is available")
        return blueprint

'''+s[insert:]
# Public minimal failures never mutate externally supplied report-bearing exceptions.
needle='''        except Exception as error:
            original_error = error
'''
s=s.replace(needle,'''        except Exception as error:
            if operation is _compile_execution and isinstance(error, ContainerBuildError):
                raise ContainerBuildError(_safe_error_message(error), code=error.code, path=error.path) from None
            original_error = error
''',1)
# Private harness type narrowing only.
s=s.replace('''                plan, fingerprint, labels, paths = _observe_plan(plan, instrumentation, self._owner_token)''','''                plan, fingerprint, labels, paths = _observe_plan(cast(_PlanSet, plan), instrumentation, self._owner_token)''')
s=s.replace('''                    plan, instrumentation, cast(str, self._parent.container._owned_token), self._parent''','''                    cast(_PlanSet, plan), instrumentation, cast(str, self._parent.container._owned_token), self._parent''')
s=s.replace('if explain_metadata and not self._parent._plan.explain_metadata:', 'if explain_metadata and not self._parent.explain_metadata_enabled:')
p.write_text(s)
p=Path('tests/test_analysis_pipeline.py');s=p.read_text().replace('monkeypatch.setattr(compiler._Compiler, "compile", fail)','monkeypatch.setattr(compiler._Compiler, "compile_execution" if operation == "build" else "compile", fail)');p.write_text(s)
p=Path('tests/test_policies.py');s=p.read_text().replace('    Scope,\n','    Scope,\n    ScopeBuilder,\n').replace('parent.create_runtime().new_scope_builder()', 'ScopeBuilder._from_blueprint(parent.create_runtime(), parent._composition_blueprint)');p.write_text(s)
