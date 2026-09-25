import json
from typing import Generic, Mapping, TypeVar

import pytest

from clean_ioc import ContainerBuilder, ContainerBuildError, Provider
from clean_ioc.cli import main


def _summary(report, implementation):
    return next(item for item in report.definitions if item.definition.implementation.endswith(implementation))


def test_census_separates_root_dependency_collection_and_named_rejection():
    class Service:
        pass

    class Default(Service):
        pass

    class Named(Service):
        pass

    class Single:
        def __init__(self, service: Service):
            pass

    class Many:
        def __init__(self, services: list[Service]):
            pass

    builder = ContainerBuilder()
    default_id = builder.register(Service, Default)
    named_id = builder.register(Service, Named, name="named")
    builder.register(Single)
    builder.register(Many)
    builder.mark_entrypoint(Single)
    builder.mark_entrypoint(Many)
    graph = builder.build().graph

    focused = graph.selection_census()
    default = _summary(focused, ".Default")
    named = _summary(focused, ".Named")
    assert focused.view == "entrypoints"
    assert default.dependency_requests == 1
    assert default.collection_inclusions == 1
    assert default.root_requests == 0
    assert named.dependency_requests == 0
    assert named.rejected_requests == 2
    assert named.collection_inclusions == 0

    all_roots = graph.selection_census(all_roots=True)
    assert _summary(all_roots, ".Named").root_requests == 2
    assert _summary(all_roots, ".Default").dependency_requests >= 1
    assert graph.selection_census().to_json() == focused.to_json()
    assert default_id not in focused.to_json()
    assert named_id not in focused.to_json()
    assert "no recorded request" in json.dumps(focused.to_dict()) or focused.complete


def test_census_keeps_global_and_boundary_marked_root_decisions_separate():
    from clean_ioc import Boundary, Expose

    class Service:
        pass

    class Global(Service):
        pass

    class GlobalNamed(Service):
        pass

    class Local(Service):
        pass

    class LocalNamed(Service):
        pass

    def install(builder):
        builder.register(Service, Local)
        builder.register(Service, LocalNamed, name="named")
        builder.mark_entrypoint(Service)

    builder = ContainerBuilder()
    builder.register(Service, Global)
    builder.register(Service, GlobalNamed, name="named")
    builder.mark_entrypoint(Service)
    builder.install_boundary(Boundary("local", install, exposes=(Expose(Service),)))
    graph = builder.build().graph
    report = graph.selection_census()
    global_named = _summary(report, ".GlobalNamed")
    local_named = _summary(report, ".LocalNamed")
    assert global_named.rejected_requests == 1
    assert local_named.rejected_requests == 1
    assert not global_named.examples[0].path.startswith("boundary:")
    assert any(use.path.startswith("boundary:local/") for use in local_named.examples)
    with pytest.raises(ValueError, match="explain-ambiguous-root"):
        graph.explain(Service)


def test_all_roots_identifies_public_and_boundary_local_contexts():
    from clean_ioc import Boundary, Expose

    class Service:
        pass

    def install(builder):
        builder.register(Service)
        builder.mark_entrypoint(Service)

    builder = ContainerBuilder()
    builder.install_boundary(Boundary("inner", install, exposes=(Expose(Service),)))
    report = builder.build().graph.selection_census(all_roots=True)
    summary = _summary(report, ".Service")
    assert summary.root_requests == 2
    assert len(report.analyzed_roots) == 2
    assert any(root.startswith("boundary:inner:") for root in report.analyzed_roots)
    assert {use.area for use in summary.examples if use.outcome == "root-selected"} == {None, "inner"}


def test_marked_collection_root_is_a_root_collection_inclusion():
    class Service:
        pass

    builder = ContainerBuilder()
    builder.register(Service)
    builder.mark_entrypoint(list[Service])
    summary = _summary(builder.build().graph.selection_census(), ".Service")
    assert summary.root_requests == 0
    assert summary.root_collection_inclusions == 1
    assert summary.collection_inclusions == 0
    assert summary.examples[0].outcome == "root-collection-included"


def test_failed_census_counts_recorded_attempt_selections_as_lower_bounds():
    class Good:
        pass

    class Missing:
        pass

    class Bad:
        def __init__(self, good: Good, missing: Missing):
            pass

    builder = ContainerBuilder()
    builder.register(Good)
    builder.register(Bad)
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    report = raised.value.selection_census()
    good = _summary(report, ".Good")
    assert good.attempt_selected == 2
    assert good.recorded_requests == 2
    assert not report.complete
    assert "Primary attempt: 2 recorded selected outcomes" in report.to_text()
    assert "Selected by 0" not in report.to_text()


def test_census_keeps_unspecialized_pattern_and_closed_selection_distinct():
    item = TypeVar("item")

    class Repository(Generic[item]):
        pass

    class Order:
        pass

    class App:
        def __init__(self, repository: Repository[Order]):
            pass

    builder = ContainerBuilder()
    builder.register_pattern(Repository[item], factory=Repository)
    builder.register(App)
    builder.mark_entrypoint(App)
    census = builder.build().graph.selection_census()
    pattern = next(item for item in census.definitions if item.definition.kind == "registration-pattern")
    assert pattern.dependency_requests == 1
    assert pattern.closed_specializations == (
        f"{Repository.__module__}.{Repository.__qualname__}[" f"{Order.__module__}.{Order.__qualname__}]",
    )

    unused_builder = ContainerBuilder()
    unused_builder.register_pattern(Repository[item], factory=Repository)
    unused = unused_builder.build().graph.selection_census()
    unused_pattern = next(item for item in unused.definitions if item.definition.kind == "registration-pattern")
    assert unused_pattern.recorded_requests == 0
    assert unused_pattern.closed_specializations == ()


def test_census_reports_recorded_eligible_alternatives_without_rerunning_filters():
    class Service:
        pass

    class First(Service):
        pass

    class Second(Service):
        pass

    class App:
        def __init__(self, service: Service):
            pass

    calls = 0

    def eligible(_component):
        nonlocal calls
        calls += 1
        return True

    builder = ContainerBuilder()
    builder.register(Service, First, when=eligible)
    builder.register(Service, Second, when=eligible)
    builder.register(App)
    builder.mark_entrypoint(App)
    graph = builder.build().graph
    build_calls = calls
    census = graph.selection_census()
    assert calls == build_calls
    assert sum(item.eligible_not_selected for item in census.definitions) == 1
    assert sum(item.dependency_requests for item in census.definitions) == 1
    assert graph.selection_census().to_json() == census.to_json()
    assert calls == build_calls


def test_census_separates_known_pattern_precedence_from_filter_rejection():
    item = TypeVar("item")

    class Serializer(Generic[item]):
        pass

    class App:
        def __init__(self, serializer: Serializer[int]):
            pass

    builder = ContainerBuilder()
    builder.register_pattern(Serializer[item], factory=Serializer)
    builder.register(Serializer[int], factory=Serializer)
    builder.register(App)
    builder.mark_entrypoint(App)
    census = builder.build().graph.selection_census()
    pattern = next(item for item in census.definitions if item.definition.kind == "registration-pattern")
    assert pattern.precedence_exclusions >= 1
    assert pattern.rejected_requests == 0
    assert any("pattern-shadowed-by-exact" in use.reason_codes for use in pattern.examples)


def test_census_boundary_alias_links_to_one_source_registration():
    from clean_ioc import Boundary, BoundaryAlias, Expose

    class Private:
        pass

    class Public:
        pass

    def install(builder):
        builder.register(Private)

    builder = ContainerBuilder()
    builder.install_boundary(Boundary("source", install, exposes=(Expose(Private, alias=BoundaryAlias(Public)),)))
    census = builder.build().graph.selection_census(all_roots=True)
    source = next(item for item in census.definitions if item.definition.service.endswith(".Private"))
    alias = next(item for item in census.definitions if item.definition.kind == "boundary-alias")
    assert alias.definition.source == source.definition.reference
    assert alias.definition.boundary == "source"
    assert alias.root_requests == 0
    assert not source.closed_specializations


def test_census_bounds_examples_without_truncating_counts():
    class Service:
        pass

    builder = ContainerBuilder()
    builder.register(Service)
    for index in range(12):

        def init(self, service: Service):
            pass

        consumer = type(f"Consumer{index}", (), {"__init__": init})
        builder.register(consumer)
        builder.mark_entrypoint(consumer)
    service = _summary(builder.build().graph.selection_census(), ".Service")
    assert service.dependency_requests == 12
    assert len(service.examples) == 8
    assert service.omitted_examples == 4


def test_census_links_generated_decorator_to_source_and_template():
    from clean_ioc import DecoratorTemplate, DerivedServices

    class Source:
        pass

    class Target:
        pass

    class Wrapper:
        def __init__(self, inner: Target):
            pass

    builder = ContainerBuilder()
    builder.register(Source)
    builder.register(Target)
    builder.register_decorator_template(
        for_each=Source,
        template=lambda _source: DecoratorTemplate(DerivedServices(Target), Wrapper),
    )
    census = builder.build().graph.selection_census(all_roots=True)
    by_kind = {item.definition.kind: item for item in census.definitions}
    generated = by_kind["generated-decorator"]
    assert generated.definition.source in {item.definition.reference for item in census.definitions}
    assert generated.definition.template == by_kind["decorator-template"].definition.reference
    assert generated.applicable_decorators == 1
    assert by_kind["decorator-template"].template_source_matches == 1


def test_census_per_call_target_is_separate_from_root_selection():
    class Service:
        def run(self) -> None:
            pass

    class Impl(Service):
        def run(self) -> None:
            pass

    builder = ContainerBuilder()
    builder.register(Service, Impl, scope="per_call")
    builder.mark_entrypoint(Service)
    graph = builder.build().graph
    included = _summary(graph.selection_census(), ".Impl")
    excluded = _summary(graph.selection_census(include_deferred=False), ".Impl")
    assert included.root_requests == 1
    assert included.deferred_target_uses == 1
    assert excluded.root_requests == 1
    assert excluded.deferred_target_uses == 0


def test_census_provider_map_reports_deferred_member_without_key():
    from clean_ioc import ProviderMapGroup

    class Service:
        pass

    class Impl(Service):
        pass

    class App:
        def __init__(self, entries: Mapping[str, Provider[Service]]):
            pass

    group = ProviderMapGroup("services", str, Service)
    builder = ContainerBuilder()
    builder.register(Service, Impl, contributes={group: "private-map-key"})
    builder.register_provider_map(group)
    builder.register(App)
    builder.mark_entrypoint(App)
    graph = builder.build().graph
    report = graph.selection_census()
    assert _summary(report, ".Impl").collection_inclusions == 1
    assert _summary(graph.selection_census(include_deferred=False), ".Impl").collection_inclusions == 0
    assert "private-map-key" not in report.to_json()


def test_census_excludes_deferred_targets_and_records_applicability():
    class Service:
        pass

    class Wrapper:
        def __init__(self, inner: Service):
            pass

    class App:
        def __init__(self, get_service: Provider[Service]):
            pass

    def configure():
        pass

    builder = ContainerBuilder()
    builder.register(Service)
    builder.register_decorator(Service, Wrapper, decorated_arg="inner")
    builder.pre_configure(Service, configure)
    builder.register(App)
    builder.mark_entrypoint(App)
    graph = builder.build().graph

    included = graph.selection_census()
    excluded = graph.selection_census(include_deferred=False)
    assert _summary(included, ".Service").deferred_target_uses >= 1
    assert _summary(excluded, ".Service").deferred_target_uses == 0
    assert _summary(included, ".Wrapper").applicable_decorators >= 1
    assert _summary(included, ".configure").applicable_pre_configurations >= 1


def test_failed_census_keeps_structural_failure_and_unexamined_outcomes():
    class Missing:
        pass

    class Service:
        def __init__(self, missing: Missing):
            pass

    calls = 0

    def forbidden(_component):
        nonlocal calls
        calls += 1
        raise AssertionError("selection predicate must not run")

    builder = ContainerBuilder()
    builder.register(Service, when=forbidden)
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    census = raised.value.selection_census()
    assert not census.complete
    assert not census.to_dict()["totals_exact"]
    assert _summary(census, ".Service").failed_requests >= 1
    assert calls == 0
    assert "Not selected in this view" not in census.to_text()


def test_census_cli_reports_partial_failure_and_redacts_values(tmp_path, monkeypatch, capsys):
    source = tmp_path / "census_example.py"
    source.write_text(
        "from clean_ioc import ContainerBuilder\n"
        "class Missing: pass\n"
        "class App:\n"
        "    def __init__(self, missing: Missing): pass\n"
        "def build():\n"
        "    builder = ContainerBuilder()\n"
        "    builder.register(App)\n"
        "    return builder\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    assert main(["census", "census_example:build", "--format", "json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["complete"] is False
    assert payload["definitions"]
    assert "_identity" not in json.dumps(payload)
