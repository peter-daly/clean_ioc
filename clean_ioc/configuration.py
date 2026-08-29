"""Public configuration primitives for Clean IoC composition."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeAlias

from .utils import singleton

__all__ = [
    "EMPTY",
    "DependencyConfig",
    "DependencySettings",
    "ParameterValueFactory",
    "RemoveDependencySetting",
    "SubDependencies",
    "Tag",
]


@singleton
class _Empty:
    def __bool__(self) -> bool:
        return False


@singleton
class _Unknown:
    def __bool__(self) -> bool:
        return False


EMPTY = _Empty()
UNKNOWN = _Unknown()


class _RemoveDependencySetting:
    """Sentinel used to remove one dependency override from a component patch."""

    def __repr__(self) -> str:
        return "RemoveDependencySetting"


RemoveDependencySetting = _RemoveDependencySetting()


def default_parameter_value_factory(default_value: Any, _: Any) -> Any:
    return default_value


def default_component_filter(component: Any) -> bool:
    return component.name is None


def default_component_list_modifier(components: list[Any]) -> list[Any]:
    return components


@dataclass
class Tag:
    name: str
    value: str | None = None

    def __iter__(self):
        yield self.name
        if self.value is not None:
            yield self.value


@dataclass(kw_only=True)
class DependencySettings:
    value_factory: Callable[[Any, Any], Any] = default_parameter_value_factory
    filter: Callable[[Any], bool] = default_component_filter
    list_modifier: Callable[[list[Any]], list[Any]] = default_component_list_modifier


DependencyConfig: TypeAlias = dict[str, Any]
SubDependencies: TypeAlias = dict[str, DependencySettings]
RegistrationFilter: TypeAlias = Callable[[Any], bool]
NodeFilter: TypeAlias = Callable[[Any], bool]
ParameterValueFactory: TypeAlias = Callable[[Any, Any], Any]
RegistrationListModifier: TypeAlias = Callable[[list[Any]], list[Any]]
