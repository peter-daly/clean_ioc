"""Application-style bundle acceptance across the final public build modes."""

import pytest

from clean_ioc import (
    AnalysisResult,
    BuildIssue,
    ComponentBuilder,
    ContainerBuilder,
    Expose,
    IssueSeverity,
    Provider,
)
from clean_ioc.bundles import BaseBundle


@pytest.mark.parametrize("mode", ["run", "analysis"])
def test_private_deferred_command_and_saga_bundle_discovery_and_validation(mode):
    activations = []
    selections = []
    rules = []

    class CommandHandler:
        def __init__(self):
            activations.append("handler")

        def handle(self):
            return "handled"

    class AuditedHandler:
        def __init__(self, inner: CommandHandler):
            activations.append("audit")
            self.inner = inner

        def handle(self):
            return "audited:" + self.inner.handle()

    class Saga:
        def __init__(self, handler: Provider[CommandHandler]):
            activations.append("saga")
            self.handler = handler

        def run(self):
            return self.handler().handle()

    def selected(component):
        selections.append(component.id)
        return True

    def required(context):
        rules.append("build")
        assert context.boundary == "commands"
        assert context.graph.diagnostics_enabled
        assert context.graph.manifest(all_roots=True).fingerprint
        return ()

    def full(context):
        rules.append("validation")
        assert context.boundary == "commands"
        return (BuildIssue("application-policy", IssueSeverity.error, "Explicit full validation finding"),)

    class CommandSagaBundle(BaseBundle):
        def apply(self, builder: ComponentBuilder):
            builder.register(CommandHandler, root_policy="dependency_only")
            builder.register_decorator(CommandHandler, AuditedHandler, when=selected)
            builder.register(Saga)
            builder.add_validation_rule(required)
            builder.add_validation_rule(full)

    builder = ContainerBuilder().set_provider_roots(())
    builder.create_boundary("commands", exposes=(Expose(Saga),)).apply_bundle(CommandSagaBundle())
    output = builder.analyse() if mode == "analysis" else builder.build()
    with output:
        runtime = output.create_runtime() if isinstance(output, AnalysisResult) else output
        assert activations == []
        assert rules == (["build", "validation"] if mode == "analysis" else [])
        assert not runtime.has_component(CommandHandler)
        catalogue = runtime.selected_registrations
        assert {item.implementation_type for item in catalogue} == {Saga, CommandHandler, AuditedHandler}
        captured_selections = tuple(selections)
        with runtime.new_scope() as scope:
            assert scope.selected_registrations is catalogue
            saga = scope.resolve(Saga)
            assert activations == ["saga"]
            assert saga.run() == "audited:handled"
        assert activations == ["saga", "handler", "audit"]
        if mode == "analysis":
            assert isinstance(output, AnalysisResult)
            for _ in range(2):
                report = output.report
                assert [issue.code for issue in report.errors] == ["application-policy"]
            assert rules == ["build", "validation"]
        else:
            assert not hasattr(runtime, "build_report")
            assert rules == []
        assert tuple(selections) == captured_selections
        assert runtime.selected_registrations is catalogue
