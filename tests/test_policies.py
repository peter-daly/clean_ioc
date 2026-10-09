import json
from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from typing import Any, Generic, TypeVar, cast

import pytest
from typing_extensions import TypeAliasType

import clean_ioc.component_filters as cf
from clean_ioc import (
    BuildIssue,
    Component,
    Container,
    ContainerBuilder,
    ContainerBuildError,
    Expose,
    IssueSeverity,
    Provider,
    ProviderMapGroup,
    ResolutionContext,
    Scope,
    Tag,
    ValidationContext,
    ValidationRule,
    select,
)
from clean_ioc.cli import main
from clean_ioc.policies import (
    Layer,
    PolicyPack,
    capability_boundary,
    forbid_dependency,
    forbid_runtime_access,
    layering,
    require_decorator,
    require_lifespan,
    require_tags,
)
from clean_ioc.tooling import qualified_name


def errors(builder: ContainerBuilder) -> tuple[BuildIssue, ...]:
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    assert raised.value.report is not None
    return raised.value.report.errors


def test_pack_freezes_a_list_and_honors_default_and_per_rule_modes_without_replaying_build_rules():
    calls: list[str] = []

    def record(name: str) -> ValidationRule:
        def rule(context: ValidationContext):
            calls.append(name)
            assert len(context.graph.roots) == 1
            yield BuildIssue(name, IssueSeverity.warning, name)

        return rule

    class Service:
        def __init__(self):
            raise AssertionError("Policies must not activate services")

    rules = [record("default"), (record("build"), "build"), (record("validation"), "validation")]
    pack = PolicyPack("architecture", cast(Any, rules), mode="validation")
    rules.clear()
    builder = ContainerBuilder()
    builder.register(Service)
    builder.apply_bundle(pack)
    container = builder.build()

    assert calls == ["build"]
    assert [issue.code for issue in container.build_report.warnings] == ["build"]
    assert "architecture" in container.build_report.warnings[0].message
    with pytest.raises(FrozenInstanceError):
        setattr(pack, "mode", "build")

    report = container.validation_report()
    assert calls == ["build", "default", "validation"]
    assert [issue.code for issue in report.warnings] == ["build", "default", "validation"]
    container.validation_report()
    assert calls == ["build", "default", "validation", "default", "validation"]


def test_pack_default_build_mode_and_parent_first_overlay_inheritance():
    class Service:
        pass

    def finding(code: str) -> ValidationRule:
        def rule(_: ValidationContext):
            yield BuildIssue(code, IssueSeverity.warning, code)

        return rule

    builder = ContainerBuilder()
    builder.register(Service)
    builder.apply_bundle(PolicyPack("parent", [finding("parent")]))
    container = builder.build()
    overlay = container.new_scope_builder()
    overlay.apply_bundle(PolicyPack("child", [finding("child"), (finding("extra"), "validation")]))
    scope = overlay.build()
    assert [issue.code for issue in scope.build_report.warnings] == ["parent", "child"]
    assert [issue.code for issue in scope.validation_report().warnings] == ["parent", "child", "extra"]


def test_inherited_policy_detects_an_overlay_lifespan_override():
    class Service:
        pass

    builder = ContainerBuilder()
    builder.register(Service, lifespan="singleton")
    builder.apply_bundle(PolicyPack("lifespans", [require_lifespan(cf.service_type_is(Service), "singleton")]))
    overlay = builder.build().new_scope_builder()
    overlay.register(Service, lifespan="scoped")
    with pytest.raises(ContainerBuildError) as raised:
        overlay.build()
    assert raised.value.report is not None
    assert [issue.code for issue in raised.value.report.errors] == ["policy-invalid-lifespan"]


def test_pack_is_usable_on_a_boundary_and_respects_existing_rule_visibility():
    class Service:
        pass

    builder = ContainerBuilder()
    builder.register(Service)
    boundary = builder.create_boundary("feature", exposes=(Expose(Service),))
    boundary.register(Service, lifespan="singleton")
    boundary.apply_bundle(PolicyPack("feature", [require_lifespan(cf.service_type_is(Service), "singleton")]))
    assert builder.build().build_report.is_valid


@pytest.mark.parametrize(
    ("name", "rules", "mode", "exception"),
    [
        ("", [], "build", ValueError),
        ("pack", [None], "build", TypeError),
        ("pack", [(lambda _: (),)], "build", TypeError),
        ("pack", [(lambda _: (), "other")], "build", ValueError),
        ("pack", [], "other", ValueError),
    ],
)
def test_pack_rejects_invalid_configuration(name, rules, mode, exception):
    with pytest.raises(exception):
        PolicyPack(name, rules, mode=mode)


def test_pack_rejects_async_callbacks_including_callable_objects():
    async def asynchronous(_: ValidationContext):
        return ()

    async def asynchronous_generator(_: ValidationContext):
        yield BuildIssue("error", IssueSeverity.error, "error")

    class AsynchronousRule:
        async def __call__(self, _: ValidationContext):
            return ()

    for rule in (asynchronous, asynchronous_generator, AsynchronousRule()):
        with pytest.raises(TypeError, match="synchronous"):
            PolicyPack("async", [cast(Any, rule)])


def test_bad_pack_rule_and_filter_failures_do_not_stop_later_rules():
    class Service:
        pass

    def malformed(_: ValidationContext):
        return [None]

    def bad_filter(_: Component) -> bool:
        raise RuntimeError("broken matcher")

    builder = ContainerBuilder()
    builder.register(Service)
    builder.apply_bundle(
        PolicyPack(
            "errors",
            [
                cast(Any, malformed),
                require_tags(bad_filter, Tag("owner", "platform")),
                require_tags(cf.service_type_is(Service), Tag("owner", "platform")),
            ],
        )
    )
    assert [issue.code for issue in errors(builder)] == [
        "validation-rule-error",
        "validation-rule-error",
        "policy-missing-tag",
    ]


def test_require_decorator_checks_exact_types_counts_and_only_registration_nodes():
    class Service:
        pass

    class TracedService(Service):
        def __init__(self, inner: Service):
            self.inner = inner

    for actual, required, code in (
        (0, 1, "policy-missing-decorator"),
        (1, 1, None),
        (2, 1, "policy-decorator-count"),
        (0, 0, None),
        (1, 0, "policy-decorator-count"),
    ):
        builder = ContainerBuilder()
        builder.register(Service)
        for _ in range(actual):
            builder.register_decorator(Service, TracedService, decorated_arg="inner")
        builder.add_validation_rule(
            require_decorator(cf.service_type_is(Service), decorator_type=TracedService, count=required)
        )
        if code is None:
            assert builder.build().build_report.is_valid
        else:
            assert [issue.code for issue in errors(builder)] == [code]

    class Impostor(Service):
        def __init__(self, inner: Service):
            self.inner = inner

    Impostor.__name__ = TracedService.__name__
    builder = ContainerBuilder()
    builder.register(Service)
    builder.register_decorator(Service, Impostor, decorated_arg="inner")
    builder.add_validation_rule(require_decorator(cf.service_type_is(Service), decorator_type=TracedService))
    assert [issue.code for issue in errors(builder)] == ["policy-missing-decorator"]


def test_require_decorator_matches_exact_closed_generic_and_transparent_type_aliases():
    item = TypeVar("item")

    class Service(Generic[item]):
        pass

    class Wrapper(Service[item]):
        def __init__(self, inner: Service[item]):
            self.inner = inner

    alias = TypeAliasType("alias", Wrapper[int])
    for expected, passes in ((Wrapper[int], True), (alias, True), (Wrapper[str], False), (Wrapper, False)):
        builder = ContainerBuilder()
        builder.register(Service[int])
        builder.register_decorator(Service, Wrapper, decorated_arg="inner")
        builder.add_validation_rule(require_decorator(cf.service_type_is(Service[int]), decorator_type=expected))
        if passes:
            assert builder.build().build_report.is_valid
        else:
            assert [issue.code for issue in errors(builder)] == ["policy-missing-decorator"]


@pytest.mark.parametrize("lifespan", ["transient", "per_resolution", "scoped", "singleton"])
def test_require_lifespan_supports_all_public_values_and_multiple_allowed_lifespans(lifespan):
    class Service:
        pass

    builder = ContainerBuilder()
    builder.register(Service, lifespan=lifespan)
    builder.add_validation_rule(require_lifespan(cf.service_type_is(Service), lifespan, "transient"))
    assert builder.build().build_report.is_valid


def test_require_tags_checks_exact_pairs_including_none_and_aggregates_missing_tags():
    class Service:
        pass

    for tags, passes in (
        ((Tag("owner", "platform"), Tag("public")), True),
        ((Tag("owner", "other"), Tag("public")), False),
        ((Tag("owner", "platform"), Tag("public", "yes")), False),
        ((), False),
    ):
        builder = ContainerBuilder()
        builder.register(Service, tags=tags)
        builder.add_validation_rule(require_tags(cf.service_type_is(Service), Tag("owner", "platform"), Tag("public")))
        if passes:
            assert builder.build().build_report.is_valid
        else:
            assert [issue.code for issue in errors(builder)] == ["policy-missing-tag"]


@pytest.mark.parametrize("shape", ["constructor", "factory", "collection", "provider", "provider-map"])
def test_direct_dependency_policies_cover_synthetic_bridges_and_factory_dependencies(shape):
    class Dependency:
        pass

    if shape == "collection":

        class Service:
            def __init__(self, dependency: list[Dependency]):
                self.dependency = dependency

    elif shape == "provider":

        class Service:
            def __init__(self, dependency: Provider[Dependency]):
                self.dependency = dependency

    elif shape == "provider-map":

        class Service:
            def __init__(self, dependency: Mapping[str, Provider[Dependency]]):
                self.dependency = dependency

    else:

        class Service:
            def __init__(self, dependency: Dependency):
                self.dependency = dependency

    Dependency.__module__ = "example.infrastructure"
    Service.__module__ = "example.domain"
    builder = ContainerBuilder()
    group = ProviderMapGroup("dependencies", str, Dependency)
    builder.register(Dependency, contributes={group: "primary"})
    if shape == "provider-map":
        builder.register_provider_map(group)

    def factory(dependency: Dependency) -> Service:
        raise AssertionError("Policies must not activate factories")

    if shape == "factory":
        builder.register(Service, factory=factory)
    else:
        builder.register(Service)
    builder.add_validation_rule(forbid_dependency(cf.service_type_is(Service), cf.service_type_is(Dependency)))
    builder.add_validation_rule(
        layering(
            layers=(
                Layer("domain", ("example.domain",)),
                Layer("infrastructure", ("example.infrastructure",)),
            ),
            allowed_dependencies={"domain": {"domain"}, "infrastructure": {"infrastructure"}},
        )
    )
    findings = errors(builder)
    assert [issue.code for issue in findings] == ["policy-forbidden-dependency", "policy-layer-violation"]
    assert all(issue.path[0] == qualified_name(Service) for issue in findings)
    assert all(issue.path[-1] == qualified_name(Dependency) for issue in findings)


def test_transitive_dependency_policy_reports_shortest_path_once_for_each_source_occurrence():
    class Forbidden:
        pass

    class Intermediate:
        def __init__(self, forbidden: Forbidden):
            self.forbidden = forbidden

    class Source:
        def __init__(self, longer: Intermediate, direct: Forbidden):
            self.longer = longer
            self.direct = direct

    class Root:
        def __init__(self, source: Source):
            self.source = source

    builder = ContainerBuilder()
    for service in (Forbidden, Intermediate, Source, Root):
        builder.register(service)
    builder.add_validation_rule(
        forbid_dependency(cf.service_type_is(Source), cf.service_type_is(Forbidden), transitive=True)
    )
    findings = errors(builder)
    assert len(findings) == 2
    assert {issue.path for issue in findings} == {
        (qualified_name(Source), qualified_name(Forbidden)),
        (qualified_name(Root), qualified_name(Source), qualified_name(Forbidden)),
    }


def test_direct_dependency_check_does_not_cross_an_intermediate_registration():
    class Forbidden:
        pass

    class Intermediate:
        def __init__(self, forbidden: Forbidden):
            self.forbidden = forbidden

    class Source:
        def __init__(self, intermediate: Intermediate):
            self.intermediate = intermediate

    builder = ContainerBuilder()
    for service in (Forbidden, Intermediate, Source):
        builder.register(service)
    builder.add_validation_rule(forbid_dependency(cf.service_type_is(Source), cf.service_type_is(Forbidden)))
    builder.add_validation_rule(
        forbid_dependency(cf.service_type_is(Source), cf.service_type_is(Forbidden), transitive=True), mode="validation"
    )
    container = builder.build()
    report = container.validation_report()
    assert [issue.code for issue in report.errors] == ["policy-forbidden-dependency"]
    assert report.errors[0].path == (qualified_name(Source), qualified_name(Intermediate), qualified_name(Forbidden))


@pytest.mark.parametrize("context_type", [Scope, Container, ResolutionContext])
def test_runtime_access_policy_checks_transitive_context_edges(context_type):
    if context_type is Scope:

        class Adapter:
            def __init__(self, context: Scope):
                self.context = context

    elif context_type is Container:

        class Adapter:
            def __init__(self, context: Container):
                self.context = context

    else:

        class Adapter:
            def __init__(self, context: ResolutionContext):
                self.context = context

    class Domain:
        def __init__(self, adapter: Adapter):
            self.adapter = adapter

    builder = ContainerBuilder()
    builder.register(Adapter)
    builder.register(Domain)
    builder.add_validation_rule(forbid_runtime_access(cf.service_type_is(Domain)))
    findings = errors(builder)
    assert [issue.code for issue in findings] == ["policy-runtime-access"]
    assert findings[0].path == (qualified_name(Domain), qualified_name(Adapter), qualified_name(context_type))


def test_layering_uses_package_boundaries_longest_prefix_and_frozen_configuration():
    class Dependency:
        pass

    class Service:
        def __init__(self, dependency: Dependency):
            self.dependency = dependency

    Service.__module__ = "example.domain.services"
    Dependency.__module__ = "example.domain.adapters"
    layers = [Layer("domain", ("example.domain",)), Layer("adapters", ("example.domain.adapters",))]
    allowed = {"domain": {"domain", "adapters"}, "adapters": {"adapters"}}
    rule = layering(layers=layers, allowed_dependencies=allowed)
    layers.clear()
    allowed["domain"].clear()
    builder = ContainerBuilder()
    builder.register(Dependency)
    builder.register(Service)
    builder.add_validation_rule(rule)
    assert builder.build().build_report.is_valid

    Service.__module__ = "example.domain_extra"
    builder = ContainerBuilder()
    builder.register(Dependency)
    builder.register(Service)
    builder.add_validation_rule(layering(layers=[Layer("domain", ("example.domain",))], allowed_dependencies={}))
    builder.add_validation_rule(
        layering(layers=[Layer("domain", ("example.domain",))], allowed_dependencies={}, require_match=True),
        mode="validation",
    )
    report = builder.build().validation_report()
    assert [issue.code for issue in report.errors] == ["policy-unmatched-layer"]
    assert report.errors[0].path == (qualified_name(Service),)


@pytest.mark.parametrize("shape", ["decorator", "generic-decorator", "pre-configuration"])
def test_layering_checks_decorator_types_and_preconfiguration_callback_modules(shape):
    item = TypeVar("item")

    class Service(Generic[item]):
        pass

    class Wrapper(Service[item]):
        def __init__(self, inner: Service[item]):
            self.inner = inner

    def configure():
        raise AssertionError("Pre-configurations must not be activated")

    Service.__module__ = "example.domain"
    Wrapper.__module__ = "example.infrastructure"
    configure.__module__ = "example.infrastructure"
    builder = ContainerBuilder()
    builder.register(Service[int])
    if shape == "pre-configuration":
        builder.pre_configure(Service[int], configure)
    elif shape == "generic-decorator":
        builder.register_decorator(Service, Wrapper, decorated_arg="inner")
    else:
        builder.register_decorator(Service[int], Wrapper[int], decorated_arg="inner")
    builder.add_validation_rule(
        layering(
            layers=[Layer("domain", ("example.domain",)), Layer("infrastructure", ("example.infrastructure",))],
            allowed_dependencies={"domain": {"domain"}},
            require_match=True,
        )
    )
    assert [issue.code for issue in errors(builder)] == ["policy-layer-violation"]


def test_dynamically_returned_coroutines_are_closed_and_reported_as_rule_errors():
    class Service:
        pass

    pending = []

    async def asynchronous():
        return ()

    def callback(_):
        coroutine = asynchronous()
        pending.append(coroutine)
        return coroutine

    builder = ContainerBuilder()
    builder.register(Service)
    builder.apply_bundle(
        PolicyPack(
            "coroutines",
            [cast(Any, callback), require_tags(cast(Any, callback), Tag("owner"))],
        )
    )
    assert [issue.code for issue in errors(builder)] == ["validation-rule-error"] * 2
    assert len(pending) == 2
    assert all(coroutine.cr_frame is None for coroutine in pending)


def test_rules_see_selected_arguments_decorators_preconfigurations_and_unmarked_roots():
    class Dependency:
        pass

    class Selected(Dependency):
        pass

    class Service:
        def __init__(self, dependency: Dependency):
            self.dependency = dependency

    class Wrapper(Service):
        def __init__(self, inner: Service, dependency: Dependency):
            self.inner = inner
            self.dependency = dependency

    def configure(dependency: Dependency):
        raise AssertionError("Pre-configurations must not be activated")

    builder = ContainerBuilder()
    builder.register(Dependency, lifespan="singleton")
    builder.register(Dependency, Selected, name="selected", lifespan="singleton")
    builder.register(Service, arguments={"dependency": select(cf.with_name("selected"))})
    builder.register_decorator(Service, Wrapper, decorated_arg="inner")
    builder.pre_configure(Service, configure)
    builder.mark_entrypoint(Dependency)
    builder.add_validation_rule(forbid_dependency(cf.service_type_is(Service), cf.implementation_type_is(Selected)))
    builder.add_validation_rule(
        forbid_dependency(cf.service_type_is(Service), cf.service_type_is(Dependency), transitive=True)
    )
    findings = errors(builder)
    assert [issue.code for issue in findings] == ["policy-forbidden-dependency"] * 3
    assert any(qualified_name(Wrapper) in issue.path for issue in findings)
    assert any(qualified_name(configure) in issue.path for issue in findings)


@pytest.mark.parametrize("marked", [False, True])
def test_capabilities_accumulate_tags_from_root_and_all_dependencies_with_one_issue(marked):
    class Dependency:
        pass

    class Intermediate:
        def __init__(self, dependency: Provider[Dependency]):
            self.dependency = dependency

    class Entry:
        def __init__(self, intermediate: Intermediate):
            self.intermediate = intermediate

    builder = ContainerBuilder()
    builder.register(Dependency, tags=(Tag("capability", "network"), Tag("capability", "secrets")))
    builder.register(Intermediate, tags=(Tag("capability", "network"),))
    builder.register(Entry, tags=(Tag("capability", "database"),))
    if marked:
        builder.mark_entrypoint(Entry)
    builder.add_validation_rule(capability_boundary(cf.service_type_is(Entry), allow={"database"}))
    findings = errors(builder)
    assert [issue.code for issue in findings] == ["policy-capability-violation"]
    assert findings[0].path == (qualified_name(Entry),)
    assert findings[0].message.endswith("network, secrets")


def test_capability_policy_supports_collection_entrypoints_and_ignores_unselected_roots():
    class Entry:
        pass

    class Other:
        pass

    builder = ContainerBuilder()
    builder.register(Entry, tags=(Tag("capability", "network"),))
    builder.register(Other, tags=(Tag("capability", "secrets"),))
    builder.mark_entrypoint(list[Entry])
    builder.add_validation_rule(capability_boundary(cf.all_components, allow=()))
    findings = errors(builder)
    assert [issue.code for issue in findings] == ["policy-capability-violation"]
    assert findings[0].root == qualified_name(list[Entry])
    assert "network" in findings[0].message and "secrets" not in findings[0].message


def test_capabilities_do_not_infer_effects_from_names_or_other_tags():
    class NetworkClient:
        pass

    builder = ContainerBuilder()
    builder.register(NetworkClient, tags=(Tag("capability"), Tag("effect", "network")))
    builder.add_validation_rule(capability_boundary(cf.all_components, allow=()))
    assert builder.build().build_report.is_valid


def test_policies_do_not_change_manifests_or_disclose_build_inputs_and_configured_values():
    class Service:
        def __init__(self, token: str):
            self.token = token

    def compose(with_policy: bool) -> Container:
        builder = ContainerBuilder()
        builder.register(Service, arguments={"token": "secret-configured-value"})
        if with_policy:
            builder.apply_bundle(
                PolicyPack(
                    "metadata",
                    [(require_tags(cf.build_arg_is("secret-key", "secret-input"), Tag("owner", "team")), "validation")],
                )
            )
        return builder.build(build_args={"secret-key": "secret-input"})

    plain = compose(False)
    checked = compose(True)
    assert plain.graph.manifest().to_json() == checked.graph.manifest().to_json()
    assert plain.graph.manifest().fingerprint == checked.graph.manifest().fingerprint
    payload = checked.validation_report().to_json()
    assert "policy-missing-tag" in payload
    for secret in ("secret-key", "secret-input", "secret-configured-value"):
        assert secret not in payload


def test_cli_runs_validation_only_pack_rules_and_cannot_ignore_errors(monkeypatch, capsys):
    from tests import tooling_targets

    def compose() -> ContainerBuilder:
        builder = ContainerBuilder()
        builder.register(tooling_targets.Dependency)
        builder.apply_bundle(PolicyPack("cli", [(require_tags(cf.all_components, Tag("owner", "team")), "validation")]))
        return builder

    monkeypatch.setattr(tooling_targets, "policy_builder", compose, raising=False)
    assert (
        main(["check", "tests.tooling_targets:policy_builder", "--format", "json", "--ignore", "policy-missing-tag"])
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert [issue["code"] for issue in payload["issues"]] == ["policy-missing-tag"]


@pytest.mark.parametrize(
    "create",
    [
        lambda: require_decorator(cf.all_components, decorator_type=object, count=-1),
        lambda: require_decorator(cf.all_components, decorator_type=object, count=True),
        lambda: require_lifespan(cf.all_components),
        lambda: require_lifespan(cf.all_components, cast(Any, "auto")),
        lambda: require_tags(cf.all_components),
        lambda: require_tags(cf.all_components, cast(Any, "owner")),
        lambda: capability_boundary(cf.all_components, allow={""}),
        lambda: Layer("domain", ("example..domain",)),
        lambda: layering(layers=[], allowed_dependencies={}),
        lambda: layering(layers=[Layer("a", ("example.a",))], allowed_dependencies={"a": {"unknown"}}),
        lambda: layering(layers=[Layer("a", ("example.a",)), Layer("a", ("example.b",))], allowed_dependencies={}),
        lambda: layering(layers=[Layer("a", ("example",)), Layer("b", ("example",))], allowed_dependencies={}),
    ],
)
def test_policy_factories_reject_invalid_configuration(create):
    with pytest.raises(ValueError):
        create()


def test_nonboolean_matcher_return_is_a_validation_rule_error():
    class Service:
        pass

    builder = ContainerBuilder()
    builder.register(Service)
    builder.add_validation_rule(require_tags(cast(Any, lambda _: object()), Tag("owner")))
    assert [issue.code for issue in errors(builder)] == ["validation-rule-error"]
