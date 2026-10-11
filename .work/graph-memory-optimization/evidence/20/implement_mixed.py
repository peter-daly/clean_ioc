from pathlib import Path
import ast,textwrap
p=Path('clean_ioc/container.py'); s=p.read_text()
def rep(a,b,n=1):
 global s
 assert a in s,a[:100]
 s=s.replace(a,b,n)
# Required dependency generic bindings are shared; return-only requirements are analysis findings.
start=s.index('    annotations = (',s.index('def _specialized_factory_dependencies')); end=s.index('    bindings: dict[str, Any]',start)
s=s[:start]+'''    annotations = tuple(dependency.service_type for dependency in registration.dependencies.values())
    unsupported = sorted({item for annotation in annotations for item in _unsupported_factory_type_parameters(annotation)})
    if unsupported:
        raise ContainerBuildError("Unsupported generic factory dependency parameters: " + ", ".join(unsupported))
    typevars = {item.__name__: item for annotation in annotations for item in _typevars_in(annotation)}
    result_typevars = {item.__name__: item for item in _typevars_in(result_annotation)}
    if _analysis_active() and _unsupported_factory_type_parameters(result_annotation):
        _analysis_issue(ContainerBuildError("Unsupported return-only factory type parameters", code="factory-return-type-unknown"))
'''+s[end:]
# At dependency bindings completion, resolve remaining result variables separately, never interfering with wiring.
idx=s.index('    dependencies: dict[str, legacy.Dependency] = {}',s.index('def _specialized_factory_dependencies'))
s=s[:idx]+'''    if _analysis_active():
        result_bindings = dict(bindings)
        for name, typevar in result_typevars.items():
            if name in typevars:
                continue
            mapped = service_mapping.get(name, _NO_TYPEVAR_DEFAULT)
            if mapped is not _NO_TYPEVAR_DEFAULT:
                _analyse_check(_merge_factory_binding, result_bindings, typevar, mapped,
                               factory=factory, service_type=service_type, code="factory-return-type-binding")
        _analyse_check(_infer_factory_bindings, result_annotation, service_type, result_bindings, result_typevars,
                       factory=factory, service_type=service_type, code="factory-return-type-binding")
        unresolved_result = [name for name, variable in result_typevars.items()
                             if _typevars_in(_resolve_factory_typevars(variable, result_bindings))]
        if unresolved_result:
            _analysis_issue(ContainerBuildError("Unresolved return-only factory TypeVar(s): " + ", ".join(unresolved_result),
                                               code="factory-return-type-unresolved"))
        result_annotation = _resolve_factory_typevars(result_annotation, result_bindings)
'''+s[idx:]
# Return-only aliases cannot stop emitting a callable with otherwise concrete inputs.
rep('''    if annotation is not inspect.Signature.empty:
        annotation = normalize_type_alias(annotation)''','''    if annotation is not inspect.Signature.empty:
        try:
            annotation = normalize_type_alias(annotation)
        except TypeAliasNormalizationError as error:
            if _analysis_active():
                _analysis_issue(ContainerBuildError("Factory result alias could not be analysed", code=error.code))''')
# Patterns use dependency annotations for binding; return-only proofs run separately.
start=s.index('                        annotations = (',s.index('def _normalize_layer_aliases')); end=s.index('                    except patterns.PatternError',start)
s=s[:start]+'''                        annotations = tuple(normalize_type_alias(dep.service_type) for dep in registration.dependencies.values())
                        patterns.factory_bindings(canonical_service, canonical_service, annotations)
                        if any(_unsupported_factory_type_parameters(annotation) for annotation in annotations):
                            raise patterns.PatternError("Pattern factory dependencies support TypeVar parameters only")
'''+s[end:]
start=s.index('            annotations = (',s.index('    def _specialize_registration')); end=s.index('                dependencies = {}',start)
s=s[:start]+'''            annotations = tuple(dependency.service_type for dependency in registration.dependencies.values())
            try:
                bindings = patterns.factory_bindings(registration.service_type, requested_service_type, annotations)
                if _analysis_active() and result_annotation is not inspect.Signature.empty:
                    result = _resolve_factory_typevars(result_annotation, bindings)
                    if not patterns.equivalent(result, requested_service_type):
                        _analysis_issue(ContainerBuildError("Factory result annotation conflicts with its closed pattern service",
                                                           code="pattern-incompatible-binding"))
                    _analyse_check(patterns.factory_bindings, registration.service_type, requested_service_type,
                                   (*annotations, result_annotation), code="pattern-incompatible-binding")
                    result_annotation = result
                if any(_unsupported_factory_type_parameters(annotation) for annotation in annotations):
                    raise patterns.PatternError("Pattern factory dependencies support TypeVar parameters only")
'''+s[end:]
# Explicit decorated keywords are concrete edges, even if absent in the signature.
start=s.index('        if definition.decorated_arg not in dependencies:',s.index('def _materialize_decorator')); end=s.index('        decorated_arg = definition.decorated_arg',start)
s=s[:start]+'''        if definition.decorated_arg not in dependencies:
            if _analysis_active():
                _analysis_issue(ContainerBuildError(f"Decorator {label} has no argument named {definition.decorated_arg!r}",
                                                   code="invalid-decorator"))
            dependencies[definition.decorated_arg] = legacy.Dependency(
                definition.decorated_arg, source, service_type, legacy.DependencySettings(), legacy.EMPTY)
'''+s[end:]
# Explicit annotation compatibility has no role where no generic binding depends on it.
start=s.index('    if not isinstance(source, type):',s.index('def _materialize_decorator')); end=s.index('    specialized_dependencies =',start)
block=s[start:end].replace('if not isinstance(source, type):','if _analysis_active() and not isinstance(source, type):').replace('raise ContainerBuildError(', '_analysis_issue(ContainerBuildError(').replace('            )\n','            ))\n')
s=s[:start]+block+s[end:]
# Ordinary decorator explicit annotations are analysis-only when unrelated to required binding.
idx=s.index('    decorated_dependency = dependencies.pop(decorated_arg)',s.index('def _materialize_decorator'))
s=s[:idx]+'''    if _analysis_active() and definition.decorated_arg is not None and not _decorated_dependency_matches(dependencies[decorated_arg].service_type, service_type):
        _analysis_issue(ContainerBuildError("Explicit decorated argument annotation is incompatible with the service", code="invalid-decorator"))
'''+s[idx:]
# Generated path has the same declared-keyword semantics.
start=s.index('        try:\n            signature_parameters = inspect.signature(signature_source).parameters',s.index('def _materialize_generated_decorator')); end=s.index('        annotation_bindings:',start)
s=s[:start]+'''        _analyse_check(_validate_dependency_names, signature_source, dependencies, code="invalid-decorator")
'''+s[end:]
rep('''        if decorated_arg not in dependencies:
            raise _GeneratedDecoratorValidationError(f"No argument named {decorated_arg!r}")
        bindings = _bind_typevar_identities(annotations[decorated_arg], definition.service_type)
        if bindings is None:
            raise _GeneratedDecoratorValidationError("Decorated argument conflicts with the projected target contract")''','''        if decorated_arg not in dependencies:
            if _analysis_active():
                _analysis_issue(ContainerBuildError(f"No decorated argument named {decorated_arg!r}", code="invalid-decorator"))
            dependencies[decorated_arg] = legacy.Dependency(decorated_arg, signature_source, definition.service_type,
                                                            legacy.DependencySettings(), legacy.EMPTY)
            annotations[decorated_arg] = definition.service_type
        bindings = _bind_typevar_identities(annotations[decorated_arg], definition.service_type)
        if bindings is None:
            if _analysis_active():
                _analysis_issue(ContainerBuildError("Decorated argument conflicts with the projected target contract", code="invalid-decorator"))
            bindings = {}''')
# Unresolved decorated-only typevars do not prevent emitting an explicitly bound target edge.
rep('unresolved = {variable for annotation in resolved.values() for variable in _typevar_identities(annotation)}', 'unresolved = {variable for name, annotation in resolved.items() if name != decorated_arg for variable in _typevar_identities(annotation)}')
rep('''        else:
            result_type = _resolve_typevar_identities(_factory_result_annotation(source), bindings)''','''        elif _analysis_active():
            result_type = _resolve_typevar_identities(_factory_result_annotation(source), bindings)''')
rep('''                    raise _GeneratedDecoratorValidationError(
                        "Decorator result is incompatible with the projected target contract"
                    )''','''                    _analysis_issue(ContainerBuildError(
                        "Decorator result is incompatible with the projected target contract", code="invalid-decorator"
                    ))''')
# Gate all policy-finding conditionals before they compute the proof or format an error.
# The nearest if contains only reporting in the policy branches below.
tree=ast.parse(s); parents={child:node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
changes={}; lines=s.splitlines(True); offsets=[0]
for line in lines: offsets.append(offsets[-1]+len(line))
for node in ast.walk(tree):
    if not isinstance(node,ast.Expr) or not isinstance(node.value,ast.Call) or not isinstance(node.value.func,ast.Name) or node.value.func.id!='_analysis_issue': continue
    parent=parents.get(node)
    if not isinstance(parent,ast.If): continue
    if len(parent.body)!=1: continue
    test=ast.get_source_segment(s,parent.test)
    if '_analysis_active()' in test: continue
    a=offsets[parent.test.lineno-1]+parent.test.col_offset; b=offsets[parent.test.end_lineno-1]+parent.test.end_col_offset
    changes[(a,b)]='_analysis_active() and ('+test+')'
for (a,b),value in sorted(changes.items(),reverse=True): s=s[:a]+value+s[b:]
# No isolated audit callback is invoked in execution compilation, including source subcompilers.
tree=ast.parse(s); lines=s.splitlines(True); offsets=[0]
for line in lines: offsets.append(offsets[-1]+len(line))
changes=[]
for node in ast.walk(tree):
    if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call):
        call=node.value
        is_check=isinstance(call.func,ast.Name) and call.func.id=='_analyse_check'
        is_captive=isinstance(call.func,ast.Attribute) and call.func.attr=='_validate_captive_lifespan'
        if not (is_check or is_captive): continue
        a=offsets[node.lineno-1]+node.col_offset; b=offsets[node.end_lineno-1]+node.end_col_offset
        raw=s[a:b]
        changes.append((a,b,'if _analysis_active():\n'+' '*(node.col_offset+4)+raw.replace('\n','\n    ')))
for a,b,value in sorted(changes,reverse=True): s=s[:a]+value+s[b:]
ast.parse(s); p.write_text(s)
s=p.read_text()
s=s.replace('            _validate_service_groups(service_type, self.groups)\n','')
s=s.replace('        _validate_service_groups(base_type, service_groups)\n','')
s=s.replace('if not isinstance(name, str) or name == "root" or not _BOUNDARY_NAME.fullmatch(name):','if not isinstance(name, str) or name == "root":')
# Minimal build budget errors do not materialize report/partial retries.
s=s.replace('''        except _BudgetStop as stop:
            error = _budget_build_error(stop, state, blueprint, diagnostics)''','''        except _BudgetStop as stop:
            if not _analysis_active():
                raise ContainerBuildError("Compilation budget exhausted", code="compilation-budget-exceeded", path=stop.path) from None
            error = _budget_build_error(stop, state, blueprint, diagnostics)''',1)
s=s.replace('''def _warmup_build_error(code: str, service: str, source: SourceLocation | None, *, plan: str | None = None):
    issue = BuildIssue(''','''def _warmup_build_error(code: str, service: str, source: SourceLocation | None, *, plan: str | None = None):
    if not _analysis_active():
        return ContainerBuildError("Warm-up target cannot be bound", code=code, path=(service,))
    issue = BuildIssue(''',1)
# Restore public preview admission (snapshot internals can also run during admitted compilation).
s=s.replace('''        blueprint, inputs = self._compilation_snapshot(build_args)
        inputs["diagnostics"] = False''','''        self._assert_mutable()
        blueprint, inputs = self._compilation_snapshot(build_args)
        inputs["diagnostics"] = False''',1)
# Build never inherits an outer analyse's policy context.
for cls in ['ContainerBuilder','ScopeBuilder']:
    start=s.index('        return self._build(',s.index('    def build(',s.index('class '+cls+'(')))
    end=s.index('\n\n    def analyse(',start)
    body=s[start:end]
    s=s[:start]+'''        token = _ANALYSIS_STATE.set(None)
        try:
'''+textwrap.indent(body,'    ')+'''
        finally:
            _ANALYSIS_STATE.reset(token)'''+s[end:]
# Prevent formatting ambiguity findings during execution.
s=s.replace('            if len(candidates) > 1:\n                path = self._current_path(', '            if _analysis_active() and len(candidates) > 1:\n                path = self._current_path(')
ast.parse(s); p.write_text(s)
