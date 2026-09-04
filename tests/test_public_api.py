import importlib.util
import inspect

import pytest

import clean_ioc
import clean_ioc.component_filters as component_filters
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
    assert {
        "INJECT",
        "REMOVE",
        "GraphVisit",
        "ParameterContext",
        "ValidationRule",
        "build_arg",
        "derive",
        "generic_arg",
        "inject",
        "select",
    }.issubset(clean_ioc.__all__)


def test_public_helpers_use_only_v2_names():
    assert "use_component" in factories.__all__
    assert "use_registered" not in factories.__all__
    assert "use_from_current_graph" not in factories.__all__

    assert "install_fastapi" in fastapi_extension.__all__
    assert "FastAPIBundle" in fastapi_extension.__all__
    assert "configure_fastapi" not in fastapi_extension.__all__
    assert "add_container_to_app" not in fastapi_extension.__all__
    assert "register_fastapi_scope_slots" not in fastapi_extension.__all__

    assert {"has_build_arg", "build_arg_is"}.issubset(component_filters.__all__)
