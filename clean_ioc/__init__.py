"""Simple IOC container.
"""
from __future__ import annotations
import abc
from collections import defaultdict, deque
from dataclasses import dataclass
import sys
import types
from enum import IntEnum
from typing import Any, ForwardRef, Type, get_type_hints
from collections.abc import Callable
from typing import _GenericAlias  # type: ignore
from uuid import uuid4
from .functional_utils import constant, fn_and, fn_not
from .type_filters import is_abstract
from .typing_utils import (
    get_generic_bases,
    get_generic_types,
    get_subclasses,
    get_typevar_to_type_mapping,
    try_to_complete_generic,
)
import inspect


class _empty:
    def __bool__(self):
        return False


class ArgInfo:
    def __init__(self, name: str, arg_type: type, default_value: Any):
        self.name = name
        self.arg_type = arg_type
        self.default_value = (
            _empty if default_value == inspect._empty else default_value
        )


def get_arg_info(subject: Callable) -> dict[str, ArgInfo]:
    arg_spec_fn = subject if inspect.isfunction(subject) else subject.__init__
    args = get_type_hints(arg_spec_fn, None, {})
    signature = inspect.signature(subject)
    d: dict[str, ArgInfo] = {}
    for name, param in signature.parameters.items():
        d[name] = ArgInfo(name=name, arg_type=args[name], default_value=param.default)
    return d


_all_registartions = constant(True)


class LifestyleType(IntEnum):
    transient = 0
    once_per_graph = 1
    scoped = 2
    singleton = 3


class CannotResolveException(Exception):
    def __init__(self):
        self.stack = deque()

    def append(self, d: Dependency):
        self.stack.appendleft(d)

    @staticmethod
    def print_dependency(d: Dependency):
        return f"implementation={d.parent_implementation}, dependant={{name={d.name}, type={d.service_type}}}))"

    @property
    def message(self):
        chain = ""
        horizontal_line = "\u2514\u2500\u2500>"
        vertical_line = "\u2502"
        spaces = " "

        root, *rest = self.stack

        chain += f"\n{CannotResolveException.print_dependency(root)}\n"

        for item in rest:
            chain += f"{spaces}{vertical_line}\n{spaces}{horizontal_line}{CannotResolveException.print_dependency(item)}\n"
            spaces += "     "

        return chain

    def __str__(self):
        return self.message


class Dependency:
    def __init__(
        self,
        name: str,
        parent_implementation: Callable | type,
        service_type: Any,
        settings: DependencySettings,
        default_value: Any,
    ):
        self.name = name
        self.parent_implementation = parent_implementation
        if isinstance(parent_implementation, type):
            self.service_type = try_to_complete_generic(
                service_type, parent_implementation
            )
        else:
            self.service_type = service_type
        self.settings = settings
        self.is_generic_list = getattr(self.service_type, "__origin__", None) == list
        self.default_value = default_value

    def resolve(self, context: ResolvingContext):
        if not self.settings.value == _empty:
            return self.settings.value

        if not self.default_value == _empty and self.settings.use_default_paramater:
            return self.default_value

        if self.is_generic_list:
            regs = context.find_registrations(self.service_type.__args__[0], self.settings.filter)  # type: ignore
            return [s.build(context) for s in regs]
        else:
            try:
                reg = context.find_registration(self.service_type, self.settings.filter)
                return reg.build(context)
            except CannotResolveException as ex:
                print(self.name)
                ex.append(self)
                raise ex


class RootDependency(Dependency):
    @staticmethod
    def __PARENT_ROOT__():
        pass

    def __init__(self, service_type: Any, settings: DependencySettings):
        super().__init__(
            name="__ROOT__",
            parent_implementation=RootDependency.__PARENT_ROOT__,
            service_type=service_type,
            settings=settings,
            default_value=_empty,
        )


class ImplementationCreator:
    def __init__(
        self,
        creator_function: Callable,
        dependency_config: dict[str, DependencySettings] = {},
    ):
        self.dependency_config = defaultdict(DependencySettings, dependency_config)
        self.creator_function = creator_function
        self.dependencies: dict[str, Dependency] = self._get_dependencies(
            self.creator_function, self.dependency_config
        )

    @classmethod
    def _get_default_value(cls, paramater: inspect.Parameter):
        default_value = _empty
        if not paramater.default == inspect._empty:
            default_value = paramater.default
        return default_value

    @classmethod
    def _get_dependencies(
        cls,
        creator_function: Callable,
        dependency_config: dict[str, DependencySettings],
    ) -> dict[str, Dependency]:
        # signature = inspect.signature(creator_function)
        args_infos = get_arg_info(creator_function)
        return {
            name: Dependency(
                name=name,
                parent_implementation=creator_function,
                service_type=arg_info.arg_type,
                settings=dependency_config[name],
                default_value=arg_info.default_value,
            )
            for name, arg_info in args_infos.items()
        }

    def create(self, context: ResolvingContext, **kwargs):
        for arg_name, arg_dep in self.dependencies.items():
            kwargs[arg_name] = arg_dep.resolve(context)
        built_instance = self.creator_function(**kwargs)
        return built_instance


class DecoratorCreator(ImplementationCreator):
    def __init__(self, service_type: type, decorator_type: type):
        self.service_type = service_type
        super().__init__(creator_function=decorator_type)
        self.decorated_arg = next(
            name
            for name, dep in self.dependencies.items()
            if dep.service_type == service_type
        )
        self.dependencies = {
            name: dep
            for name, dep in self.dependencies.items()
            if name != self.decorated_arg
        }


class Decorator:
    def __init__(
        self, service_type: type, decorator_type: type, filter: RegistartionFilter
    ):
        self.service_type = service_type
        self.decorator_type = decorator_type
        self.creator = DecoratorCreator(
            service_type=service_type, decorator_type=decorator_type
        )
        self.registartion_filter = filter

    def decorate(self, instance: Any, context: ResolvingContext):
        kwargs = {}
        kwargs[self.creator.decorated_arg] = instance
        return self.creator.create(context, **kwargs)


class Registration:
    def __init__(
        self,
        service_type: type,
        implementation: Callable,
        lifestyle: LifestyleType,
        name: str | None = None,
        dependency_config: dict[str, DependencySettings] = {},
    ):
        self.service_type = service_type
        self.implementation = implementation
        self.creator = ImplementationCreator(
            creator_function=implementation, dependency_config=dependency_config
        )
        self.lifestyle = lifestyle
        self.name = name
        self._id = str(uuid4())
        self.generic_mapping = get_typevar_to_type_mapping(self.service_type)

    @property
    def is_named(self):
        return self.name is not None

    def build(self, context: ResolvingContext):
        cached_instance = context.get_cached(self._id)
        if not cached_instance == _empty:
            return cached_instance
        built_instance = self.creator.create(context)

        for dec in context.find_decorators_that_apply(self):
            built_instance = dec.decorate(built_instance, context)

        context.new_instance_created(self._id, built_instance, self.lifestyle)
        return built_instance


class Registry:
    def __init__(self):
        self._registrations: dict[type, deque[Registration]] = defaultdict(deque)
        self._decorators: dict[type, deque[Decorator]] = defaultdict(deque)
        self._singletons: dict[str, Any] = {}

    def add_registration(self, registartion: Registration):
        self._registrations[registartion.service_type].appendleft(registartion)

    def add_decorator(self, decorator: Decorator):
        self._decorators[decorator.service_type].appendleft(decorator)

    def add_singleton_instance(self, registartion_id: str, instance: Any):
        self._singletons[registartion_id] = instance

    def get_registartions(self, service_type: type):
        return self._registrations[service_type]

    def get_decorators(self, service_type: type):
        return self._decorators[service_type]

    def get_singleton(self, registartion_id):
        return self._singletons.get(registartion_id)

    @property
    def singleton_items(self):
        return self._singletons.items()


class ResolvingContext:
    def __init__(self, registry: Registry, scope: Scope):
        self.registry = registry
        self.scope = scope
        self._cache = {}
        self._cache = {
            **{k: v for k, v in registry.singleton_items},
            **{k: v for k, v in scope.scoped_items},
        }

    def try_generic_fallback(self, service_type: _GenericAlias):
        return self.find_registration(service_type.__origin__, _all_registartions)

    def find_registration(
        self, service_type: type, registration_finder: Callable
    ) -> Registration:
        regs = self.find_registrations(service_type, registration_finder)
        reg = next(iter(regs), None)

        if reg is None:
            if type(service_type) == _GenericAlias:
                reg = self.try_generic_fallback(service_type)
            if reg is None:
                print(f"{service_type} is None")
                raise CannotResolveException()
        return reg

    def find_registrations(
        self, service_type: type, registration_filter: Callable[[Registration], bool]
    ) -> list[Registration]:
        scoped_registrations = [
            r
            for r in self.scope.get_registartions(service_type)
            if registration_filter(r)
        ]
        container_registrations = [
            r
            for r in self.registry.get_registartions(service_type)
            if registration_filter(r)
        ]
        return scoped_registrations + container_registrations

    def find_decorators_that_apply(self, registration: Registration):
        return [
            d
            for d in self.registry.get_decorators(registration.service_type)
            if d.registartion_filter(registration)
        ]

    def get_cached(self, reg_id: str):
        return self._cache.get(reg_id, _empty)

    def new_instance_created(
        self, reg_id: str, instance: Any, lifestyle: LifestyleType
    ):
        if lifestyle == LifestyleType.singleton:
            self.registry.add_singleton_instance(reg_id, instance)
        elif lifestyle == LifestyleType.scoped:
            self.scope.add_scoped_instance(reg_id, instance)

        if lifestyle >= LifestyleType.once_per_graph:
            self._cache[reg_id] = instance


class Resolver(abc.ABC):
    @abc.abstractmethod
    def resolve(
        self,
        cls: type,
        filter: RegistartionFilter = _all_registartions,
        *args,
        **kwargs,
    ) -> Any:
        pass


class Scope(Resolver):
    def __init__(
        self,
    ):
        self._registrations = defaultdict(deque)
        self._scoped_instances = {}

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        pass

    @abc.abstractmethod
    def add_scoped_instance(self, *args):
        pass

    @abc.abstractmethod
    def register(self, *args):
        pass

    def get_registartions(self, service_tyep):
        return self._registrations[service_tyep]

    @property
    def scoped_items(self):
        return self._scoped_instances.items()


class ContainerScope(Scope):
    def __init__(self, container: Container):
        self._container = container
        self._registrations = defaultdict(deque)
        self._scoped_instances = {}

        self.register(ContainerScope, instance=self)
        self.register(Resolver, instance=self)

    def register(
        self,
        service_type: type,
        impl_type: type | None = None,
        factory: Callable | None = None,
        instance: Any | None = None,
        name: str | None = None,
        dependency_config: dict[str, DependencySettings] = {},
    ):
        if instance is not None:
            self._registrations[service_type].appendleft(
                Registration(
                    service_type=service_type,
                    implementation=lambda: instance,
                    lifestyle=LifestyleType.scoped,
                    name=name,
                )
            )
        elif factory is not None:
            self._registrations[service_type].appendleft(
                Registration(
                    service_type=service_type,
                    implementation=factory,
                    lifestyle=LifestyleType.scoped,
                    name=name,
                    dependency_config=dependency_config,
                )
            )
        elif impl_type is not None:
            self._registrations[service_type].appendleft(
                Registration(
                    service_type=service_type,
                    implementation=impl_type,
                    lifestyle=LifestyleType.scoped,
                    name=name,
                    dependency_config=dependency_config,
                )
            )
        else:
            self._registrations[service_type].appendleft(
                Registration(
                    service_type=service_type,
                    implementation=service_type,
                    lifestyle=LifestyleType.scoped,
                    name=name,
                    dependency_config=dependency_config,
                )
            )

    def _before_start(self):
        pass

    def _after_finish(self):
        pass

    def __enter__(self):
        self._before_start()
        return self

    def __exit__(self, *args, **kwargs):
        self._after_finish()

    def get_registartions(self, service_tyep):
        return self._registrations[service_tyep]

    def add_scoped_instance(self, registration_id: str, instance: Any):
        self._scoped_instances[registration_id] = instance

    def resolve(
        self,
        service_type: type,
        filter: RegistartionFilter = _all_registartions,
    ):
        return self._container.resolve(
            service_type=service_type, filter=filter, scope=self
        )


class EmptyContainerScope(Scope):
    def __init__(self):
        super().__init__()

    def add_scoped_instance(self, *args):
        pass

    def register(self, *args):
        pass

    def resolve(self, *args):
        pass


class Container(Resolver):
    def __init__(self):
        self.registry = Registry()
        self.register(Container, instance=self)
        self.register(Resolver, instance=self)

    def register(
        self,
        service_type: type,
        impl_type: type | None = None,
        factory: Callable | None = None,
        instance: Any | None = None,
        lifestyle: LifestyleType = LifestyleType.once_per_graph,
        name: str | None = None,
        dependency_config: dict[str, DependencySettings] = {},
    ):
        if instance is not None:
            self.registry.add_registration(
                Registration(
                    service_type=service_type,
                    implementation=lambda: instance,
                    dependency_config=dependency_config,
                    lifestyle=LifestyleType.singleton,
                    name=name,
                )
            )
        elif factory is not None:
            self.registry.add_registration(
                Registration(
                    service_type=service_type,
                    implementation=factory,
                    dependency_config=dependency_config,
                    lifestyle=lifestyle,
                    name=name,
                )
            )
        elif impl_type is not None:
            self.registry.add_registration(
                Registration(
                    service_type=service_type,
                    implementation=impl_type,
                    dependency_config=dependency_config,
                    lifestyle=lifestyle,
                    name=name,
                )
            )
        else:
            self.registry.add_registration(
                Registration(
                    service_type=service_type,
                    implementation=service_type,
                    dependency_config=dependency_config,
                    lifestyle=lifestyle,
                    name=name,
                )
            )

    def register_subclasses(
        self,
        base_type: type,
        lifestyle: LifestyleType = LifestyleType.once_per_graph,
        type_filter: Callable[[type], bool] = constant(True),
    ):
        sub_classes = get_subclasses(base_type, type_filter)

        for sc in sub_classes:
            self.register(base_type, sc, lifestyle=lifestyle)
            self.register(sc, lifestyle=lifestyle)

    def register_decorator(
        self,
        service_type: type,
        decorator_type: type,
        registration_filter: Callable[[Registration], bool] = _all_registartions,
    ):
        self.registry.add_decorator(
            Decorator(
                service_type=service_type,
                decorator_type=decorator_type,
                filter=registration_filter,
            )
        )

    @staticmethod
    def _get_target_generic_base(generic_service_type: type, subclass: type):
        return next(
            (
                try_to_complete_generic(b, subclass)
                for b in get_generic_bases(
                    subclass,
                    lambda t: getattr(t, "__origin__", None) == generic_service_type,
                )
            ),
            None,
        )

    def register_open_generic(
        self,
        generic_service_type: type,
        fallback_type: type | None = None,
        lifestyle: LifestyleType = LifestyleType.once_per_graph,
        name: str | None = None,
        type_filter: Callable[[type], bool] = constant(True),
    ):
        full_type_filter = fn_and(fn_not(is_abstract), type_filter)
        subclasses = get_subclasses(generic_service_type, full_type_filter)
        for subclass in subclasses:
            target_generic_base = self._get_target_generic_base(
                generic_service_type, subclass
            )
            if target_generic_base:
                self.register(target_generic_base, subclass, lifestyle=lifestyle)

        if fallback_type:
            self.register(
                generic_service_type, fallback_type, lifestyle=lifestyle, name=name
            )

    def register_open_generic_decorator(
        self,
        generic_service_type: type,
        generic_decorator_type: type,
        type_filter: Callable[[type], bool] = constant(True),
    ):
        full_type_filter = fn_and(fn_not(is_abstract), type_filter)
        subclasses = get_subclasses(generic_service_type, full_type_filter)
        for subclass in subclasses:
            target_generic_base = self._get_target_generic_base(
                generic_service_type, subclass
            )
            if target_generic_base:
                generic_values = get_generic_types(target_generic_base)
                concrete_decorator = generic_decorator_type[generic_values]  # type: ignore
                DecoratedType = types.new_class(
                    f"DecoratedGeneric_{concrete_decorator.__name__}",
                    (concrete_decorator,),
                    {},
                )

                self.register_decorator(target_generic_base, DecoratedType)

    def resolve(
        self,
        service_type,
        filter: RegistartionFilter = _all_registartions,
        scope: Scope = EmptyContainerScope(),
    ) -> Any:
        d = RootDependency(service_type, DependencySettings(filter=filter))
        context = ResolvingContext(self.registry, scope)
        return d.resolve(context)

    def new_scope(
        self, ScopeClass: Type[ContainerScope] = ContainerScope, *args, **kwargs
    ) -> Scope:
        return ScopeClass(self, *args, **kwargs)

    def apply_module(self, module_fn: Callable[[Container], None]):
        module_fn(self)


@dataclass
class DependencySettings:
    value: Any = _empty
    use_default_paramater: bool = True
    filter: RegistartionFilter = _all_registartions


RegistartionFilter = Callable[[Registration], bool]
