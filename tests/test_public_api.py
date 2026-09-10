import importlib.util
import inspect
from typing import Literal

import pytest

import clean_ioc
import clean_ioc.boundaries as boundaries
import clean_ioc.component_filters as component_filters
import clean_ioc.ext.asgi as asgi_extension
import clean_ioc.ext.fastapi as fastapi_extension
import clean_ioc.factories as factories
from clean_ioc import ContainerBuilder, ScopeBuilder


@pytest.mark.parametrize(
    "module_name",
    [
        "clean_ioc.core",
        "clean_ioc.configuration",
        "clean_ioc.diagnostics",
        "clean_ioc.list_reduction_filters",
        "clean_ioc.node_filters",
        "clean_ioc.registration_filters",
        "clean_ioc.v2",
        "clean_ioc.value_factories",
    ],
)
def test_v1_modules_are_not_shipped(module_name: str):
    assert importlib.util.find_spec(module_name) is None


def test_package_root_has_one_compiled_container_surface():
    assert "ContainerBuilder" in clean_ioc.__all__
    assert "Container" in clean_ioc.__all__
    assert not {
        "CaptiveDependencyError",
        "CircularDependencyError",
        "NeedsScopedRegistrationError",
        "UNKNOWN",
        "EMPTY",
        "DependencyContext",
        "DependencySettings",
        "ParameterValueFactory",
        "SubDependencies",
    }.intersection(clean_ioc.__all__)

    builder_methods = set(dir(ContainerBuilder))
    assert not {
        "expect_to_be_scoped",
        "patch_registration",
        "register_generic_decorator",
    }.intersection(builder_methods)
    assert "parent_node_filter" not in inspect.signature(ContainerBuilder.register).parameters
    assert "dependency_config" not in inspect.signature(ContainerBuilder.register).parameters
    assert "arguments" in inspect.signature(ContainerBuilder.register).parameters
    assert "build_args" in inspect.signature(ContainerBuilder.build).parameters
    assert "build_args" in inspect.signature(ScopeBuilder.build).parameters
    assert "build_args" in inspect.signature(ContainerBuilder.has_component).parameters
    assert "build_args" in inspect.signature(ContainerBuilder.get_component_id).parameters
    assert "build_args" in inspect.signature(ContainerBuilder.get_component_ids).parameters
    assert "add_validation_rule" in builder_methods
    assert "install_boundary" in builder_methods
    assert "install_boundary" in set(dir(ScopeBuilder))
    assert "install_boundary" not in set(dir(clean_ioc.ComponentBuilder))
    assert inspect.signature(ContainerBuilder.add_validation_rule).parameters["mode"].kind is (
        inspect.Parameter.KEYWORD_ONLY
    )
    assert inspect.signature(ScopeBuilder.add_validation_rule).parameters["mode"].default == "build"
    assert clean_ioc.ValidationRuleMode == Literal["build", "validation"]
    assert tuple(inspect.signature(clean_ioc.Scope.validation_report).parameters) == ("self",)
    assert {
        "AsyncProvider",
        "Boundary",
        "INJECT",
        "REMOVE",
        "GraphVisit",
        "ParameterContext",
        "Provider",
        "ProviderScopeClosedError",
        "Expose",
        "TypeAst",
        "ValidationContext",
        "ValidationRule",
        "ValidationRuleMode",
        "Use",
        "build_arg",
        "derive",
        "generic_arg",
        "inject",
        "select",
    }.issubset(clean_ioc.__all__)


def test_boundary_api_replaces_assembly_without_aliases():
    assert clean_ioc.Boundary is boundaries.Boundary
    assert clean_ioc.Expose is boundaries.Expose
    assert clean_ioc.Use is boundaries.Use
    assert tuple(inspect.signature(clean_ioc.Boundary).parameters) == ("name", "root_bundle", "uses", "exposes")
    assert "Assembly" not in clean_ioc.__all__
    assert not hasattr(clean_ioc, "Assembly")
    assert not hasattr(boundaries, "Assembly")
    assert importlib.util.find_spec("clean_ioc.assemblies") is None
    for builder_type in (ContainerBuilder, ScopeBuilder):
        assert not hasattr(builder_type, "install_assembly")
    for metadata_type in (
        clean_ioc.Component,
        clean_ioc.GraphRoot,
        clean_ioc.GraphVisit,
        clean_ioc.DefinitionOrigin,
        clean_ioc.ValidationContext,
    ):
        assert hasattr(metadata_type, "boundary")
        assert not hasattr(metadata_type, "assembly")
    assert hasattr(clean_ioc.CompiledGraph, "boundaries")
    assert not hasattr(clean_ioc.CompiledGraph, "assemblies")


def test_public_helpers_use_only_v2_names():
    assert "use_component" in factories.__all__
    assert "use_registered" not in factories.__all__
    assert "use_from_current_graph" not in factories.__all__

    assert "install_fastapi" in fastapi_extension.__all__
    assert "FastAPIBundle" in fastapi_extension.__all__
    assert "configure_fastapi" not in fastapi_extension.__all__
    assert "add_container_to_app" not in fastapi_extension.__all__
    assert "register_fastapi_scope_slots" not in fastapi_extension.__all__

    assert "CleanIocMiddleware" in asgi_extension.__all__
    assert "ASGIBundle" in asgi_extension.__all__
    assert "get_scope" in asgi_extension.__all__
    assert "HealthCheckMiddleware" not in asgi_extension.__all__
    assert "create_health_app" not in asgi_extension.__all__

    assert {"has_build_arg", "build_arg_is"}.issubset(component_filters.__all__)
