import importlib.util
import inspect

import pytest

import clean_ioc
import clean_ioc.ext.fastapi as fastapi_extension
import clean_ioc.factories as factories
from clean_ioc import ContainerBuilder


@pytest.mark.parametrize(
    "module_name",
    [
        "clean_ioc.core",
        "clean_ioc.diagnostics",
        "clean_ioc.list_reduction_filters",
        "clean_ioc.node_filters",
        "clean_ioc.registration_filters",
        "clean_ioc.v2",
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
    }.intersection(clean_ioc.__all__)

    builder_methods = set(dir(ContainerBuilder))
    assert not {
        "expect_to_be_scoped",
        "patch_registration",
        "register_generic_decorator",
    }.intersection(builder_methods)
    assert "parent_node_filter" not in inspect.signature(ContainerBuilder.register).parameters


def test_public_helpers_use_only_v2_names():
    assert "use_component" in factories.__all__
    assert "use_registered" not in factories.__all__
    assert "use_from_current_graph" not in factories.__all__

    assert "install_fastapi" in fastapi_extension.__all__
    assert "configure_fastapi" in fastapi_extension.__all__
    assert "add_container_to_app" not in fastapi_extension.__all__
    assert "register_fastapi_scope_slots" not in fastapi_extension.__all__
