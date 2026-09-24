"""Concrete registered-service selection without decorator-template activation."""

import sys
import types
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from typing import Any, Generic, ParamSpec, Protocol, TypeVar, TypeVarTuple, cast
from typing import Callable as TypingCallable

import pytest
from typing_extensions import TypeAliasType

from clean_ioc import ContainerBuilder, ContainerBuildError, DerivedServices, ServiceGroup
from clean_ioc.container import _Blueprint, _Compiler
from clean_ioc.generic_utils import _bind_typevar_identities, _resolve_typevar_identities

T = TypeVar("T")
U = TypeVar("U")
V = TypeVar("V")
P = ParamSpec("P")
Ts = TypeVarTuple("Ts")


class Contract(Generic[T, U]):
    pass


class Reordered(Contract[U, T], Generic[T, U]):
    pass


class Fixed(Reordered[str, V]):
    pass


def compiler_for(builder):
    return _Compiler(_Blueprint((builder._layer(),)))


def selected(compiler, selector, registration_id, request, *, specialize=False):
    definition = compiler.blueprint.registration_definition(registration_id)
    assert definition is not None
    registration, layer = definition
    if specialize:
        registration = compiler._specialize_factory(registration, layer, request)
    return compiler._select_service_target(selector, registration, layer, request)


def test_reusable_immutable_automatic_selector_and_explicit_registration_identity():
    automatic = DerivedServices(Contract)
    group = ServiceGroup("handlers", service_type=Contract)
    same_name = ServiceGroup("handlers", service_type=Contract)
    with pytest.raises(FrozenInstanceError):
        setattr(automatic, "service_type", int)
    for _ in range(2):
        builder = ContainerBuilder()
        member = builder.register(Fixed[int], factory=Fixed, name="member", groups=[group])
        nonmember = builder.register(Fixed[int], factory=Fixed, name="plain", groups=[same_name])
        compiler = compiler_for(builder)
        explicit = selected(compiler, group, member, Fixed[int])
        derived = selected(compiler, automatic, member, Fixed[int])
        assert explicit == derived
        assert explicit is not None
        assert explicit.registration_id == member
        assert explicit.requested_service_type == Fixed[int]
        assert explicit.projected_contract == Contract[int, str]
        assert explicit.bindings == {T: int, U: str}
        with pytest.raises(TypeError):
            explicit.bindings[T] = bytes
        assert selected(compiler, group, nonmember, Fixed[int]) is None
        assert selected(compiler, automatic, nonmember, Fixed[int]) is not None
        assert compiler._service_groups_for(*compiler.blueprint.registration_definition(nonmember)) == frozenset(
            {same_name}
        )


def test_generated_subclass_and_alias_preserve_original_request_key():
    generated = types.new_class("Generated", (Fixed[int],))
    alias = TypeAliasType("alias", generated)
    contract_alias = TypeAliasType("contract_alias", Contract)
    group = ServiceGroup("generated", service_type=contract_alias)
    builder = ContainerBuilder()
    registration_id = builder.register(alias, groups=[group])
    compiler = compiler_for(builder)
    for selector in (group, DerivedServices(contract_alias)):
        target = selected(compiler, selector, registration_id, alias)
        assert target is not None
        assert target.requested_service_type is alias
        assert target.projected_contract == Contract[int, str]
        assert target.bindings == {T: int, U: str}
    container = builder.build()
    assert type(container.resolve(alias)) is generated
    assert Contract[int, str] not in container._plan.blueprint.service_types()


def test_actual_typevar_identity_is_retained_in_both_scopes_and_decorator_binding():
    first = TypeVar("Same")  # ty:ignore[mismatched-type-name]
    second = TypeVar("Same")  # ty:ignore[mismatched-type-name]
    decorator_variable = TypeVar("Same")  # ty:ignore[mismatched-type-name]

    class Pair(Generic[first, second]):
        pass

    selector = DerivedServices(Pair[first, second])
    builder = ContainerBuilder()
    registration_id = builder.register(Pair[int, str], factory=Pair)
    target = selected(compiler_for(builder), selector, registration_id, Pair[int, str])
    assert target is not None
    assert target.bindings == {first: int, second: str}
    assert target.declaration_bindings == {first: int, second: str}
    # A decorator declares independent variables; only structure binds them.
    bindings = _bind_typevar_identities(Pair[decorator_variable, str], target.projected_contract)
    assert bindings == {decorator_variable: int}
    assert _resolve_typevar_identities(list[decorator_variable], bindings) == list[int]
    assert first not in bindings and second not in bindings


def test_selector_variables_are_distinct_from_origin_parameters_and_repeats_are_checked():
    builder = ContainerBuilder()
    equal = builder.register(Contract[int, int], factory=Contract)
    unequal = builder.register(Contract[int, str], factory=Contract)
    compiler = compiler_for(builder)
    selector = DerivedServices(Contract[V, V])
    target = selected(compiler, selector, equal, Contract[int, int])
    assert target is not None
    assert target.bindings == {T: int, U: int}
    assert target.declaration_bindings == {V: int}
    assert selected(compiler, selector, unequal, Contract[int, str]) is None


def test_factory_and_instance_targets_never_activate_during_selection():
    calls = []

    def make() -> Fixed[int]:
        calls.append("called")
        return Fixed()

    builder = ContainerBuilder()
    group = ServiceGroup("targets", service_type=Contract)
    factory_id = builder.register(Fixed[int], factory=make, name="factory", groups=[group])
    instance = Fixed[int]()
    instance_id = builder.register(Fixed[int], instance=instance, name="instance", groups=[group])
    compiler = compiler_for(builder)
    for registration_id in (factory_id, instance_id):
        assert selected(compiler, group, registration_id, Fixed[int]) == selected(
            compiler, DerivedServices(Contract), registration_id, Fixed[int]
        )
    assert not calls


def test_unrelated_registered_contract_is_excluded_even_for_implementation_lookup_key():
    class Other:
        pass

    builder = ContainerBuilder()
    registration_id = builder.register(Other, cast(Any, Fixed[int]))
    compiler = compiler_for(builder)
    selector = DerivedServices(Contract)
    assert selected(compiler, selector, registration_id, Other) is None
    assert selected(compiler, selector, registration_id, Fixed[int]) is None


def test_nominal_protocol_derivation_only():
    class Service(Protocol[T]):
        def method(self) -> T: ...

    class Derived(Service[int], Protocol):
        pass

    class Structural:
        def method(self) -> int:
            return 1

    builder = ContainerBuilder()
    nominal = builder.register(Derived, factory=Structural)
    structural = builder.register(Structural)
    compiler = compiler_for(builder)
    target = selected(compiler, DerivedServices(Service), nominal, Derived)
    assert target is not None and target.projected_contract == Service[int]
    assert selected(compiler, DerivedServices(Service), structural, Structural) is None


def test_conflicting_paths_fail_and_consistent_diamond_projects_once():
    class Left(Contract[int, str]):
        pass

    class Right(Contract[int, str]):
        pass

    class Compatible(Left, Right):
        pass

    class Wrong(Contract[bytes, str]):
        pass

    class Ambiguous(Left, Wrong):  # ty:ignore[invalid-generic-class]
        pass

    builder = ContainerBuilder()
    compatible = builder.register(Compatible)
    ambiguous = builder.register(Ambiguous)
    compiler = compiler_for(builder)
    target = selected(compiler, DerivedServices(Contract), compatible, Compatible)
    assert target is not None and target.projected_contract == Contract[int, str]
    with pytest.raises(ContainerBuildError, match="Ambiguous service projection") as error:
        selected(compiler, DerivedServices(Contract), ambiguous, Ambiguous)
    assert error.value.code == "service-target-projection"
    # Membership must be checked before even attempting a projection.
    assert selected(compiler, ServiceGroup("empty", service_type=Contract), ambiguous, Ambiguous) is None


@pytest.mark.parametrize("factory", [False, True])
def test_open_registration_constraints_validate_actual_closed_requests(factory):
    class Service(Generic[T]):
        pass

    def make() -> Service[T]:
        return Service()

    group = ServiceGroup("integers", service_type=Service[int])
    builder = ContainerBuilder()
    registration_id = builder.register(Service, groups=[group], **({"factory": make} if factory else {}))
    compiler = compiler_for(builder)
    for selector in (group, DerivedServices(Service[int])):
        target = selected(compiler, selector, registration_id, Service[int], specialize=True)
        assert target is not None and target.bindings == {T: int}
        assert target.registration_id == registration_id
    builder.mark_entrypoint(Service[int])
    assert isinstance(builder.build().resolve(Service[int]), Service)
    builder = ContainerBuilder()
    builder.register(Service, groups=[group], **({"factory": make} if factory else {}))
    builder.mark_entrypoint(Service[str])
    with pytest.raises(ContainerBuildError, match="integers") as error:
        builder.build()
    assert error.value.report is not None
    assert any(issue.code == "service-group-incompatible" for issue in error.value.report.errors)


def test_pattern_request_retains_original_registration_id_and_enforces_fixed_contract():
    class Service(Generic[T]):
        pass

    def make() -> Service[list[T]]:
        return Service()

    group = ServiceGroup("lists", service_type=Service[list[int]])
    builder = ContainerBuilder()
    registration_id = builder.register_pattern(Service[list[T]], factory=make, groups=[group])
    compiler = compiler_for(builder)
    target = selected(compiler, group, registration_id, Service[list[int]], specialize=True)
    assert target == selected(compiler, DerivedServices(Service), registration_id, Service[list[int]], specialize=True)
    assert target is not None and target.registration_id == registration_id
    assert target.requested_service_type == Service[list[int]]

    class Consumer:
        def __init__(self, value: Service[list[int]]):
            self.value = value

    builder.register(Consumer)
    assert isinstance(builder.build().resolve(Consumer).value, Service)
    builder = ContainerBuilder()
    builder.register_pattern(Service[list[T]], factory=make, groups=[group])

    class BadConsumer:
        def __init__(self, value: Service[list[str]]):
            self.value = value

    builder.register(BadConsumer)
    with pytest.raises(ContainerBuildError, match="lists"):
        builder.build()


@pytest.mark.parametrize(
    ("contract_arg", "good_arg", "bad_arg"),
    [
        (str | int, int | str, int | bytes),
        (Callable[[str], int], Callable[[str], int], Callable[[bytes], int]),
        (dict[str, list[int]], dict[str, list[int]], dict[str, list[bytes]]),
    ],
)
def test_deferred_nested_callable_and_union_group_constraints(contract_arg, good_arg, bad_arg):
    class Service(Generic[T]):
        pass

    group = ServiceGroup("constrained", service_type=Service[contract_arg])
    builder = ContainerBuilder()
    builder.register(Service, groups=[group])
    builder.mark_entrypoint(Service[good_arg])
    builder.build()
    builder = ContainerBuilder()
    builder.register(Service, groups=[group])
    builder.mark_entrypoint(Service[bad_arg])
    with pytest.raises(ContainerBuildError, match="constrained"):
        builder.build()


def test_union_variable_matching_is_order_independent_and_rejects_ambiguity():
    assert _bind_typevar_identities(Contract[T | int, T], Contract[int | str, str]) == {T: str}
    assert _bind_typevar_identities(Contract[T | U, T], Contract[int | str, int]) == {T: int, U: str}
    with pytest.raises(ValueError, match="Ambiguous"):
        _bind_typevar_identities(Contract[T | U, bool], Contract[int | str, bool])
    assert _bind_typevar_identities(Contract[Callable[[T], U], T], Contract[Callable[[str], int], str]) == {
        T: str,
        U: int,
    }


def test_open_targets_fail_clearly_and_closed_repeated_registration_constraints_are_enforced():
    group = ServiceGroup("repeated", service_type=Contract[T, T])
    builder = ContainerBuilder()
    registration_id = builder.register(Contract, groups=[group])
    compiler = compiler_for(builder)
    with pytest.raises(ContainerBuildError, match="Unresolved"):
        selected(compiler, group, registration_id, Contract)
    builder.mark_entrypoint(Contract[int, str])
    with pytest.raises(ContainerBuildError, match="repeated"):
        builder.build()


def test_deferred_discovery_and_fallback_are_selected_using_current_snapshot():
    class Service(Generic[T]):
        pass

    group = ServiceGroup("discovered", service_type=Service[int])
    selector = DerivedServices(Service)
    builder = ContainerBuilder()
    builder.register_generic_subclasses(
        Service, groups=[group], subclass_type_filter=lambda cls: cls.__name__ == "Later"
    )

    class Later(Service[int]):
        pass

    compiler = compiler_for(builder)
    registrations = compiler.blueprint.registrations(Service[int])
    assert len(registrations) == 1
    registration, layer = registrations[0]
    assert compiler._select_service_target(group, registration, layer, Service[int]) == compiler._select_service_target(
        selector, registration, layer, Service[int]
    )
    assert isinstance(builder.build().resolve(Service[int]), Later)

    class Fallback(Service[T]):
        pass

    fallback_builder = ContainerBuilder()
    fallback_builder.register_generic_subclasses(
        Service, fallback_type=Fallback, subclass_type_filter=lambda cls: False, groups=[group]
    )
    fallback_builder.mark_entrypoint(Service[str])
    with pytest.raises(ContainerBuildError, match="discovered"):
        fallback_builder.build()


def test_existing_ordinary_decorator_does_not_gain_derived_matching():
    class Service:
        pass

    class Child(Service):
        pass

    class Decorator(Service):
        def __init__(self, wrapped: Service):
            self.wrapped = wrapped

    builder = ContainerBuilder()
    builder.register(Child)
    builder.register_decorator(Service, Decorator)
    assert type(builder.build().resolve(Child)) is Child


@pytest.mark.skipif(sys.version_info < (3, 12), reason="PEP 695 requires Python 3.12")
def test_pep695_generic_identity_and_alias_projection():
    namespace = {}
    exec(  # noqa: S102 - version-conditional Python syntax fixture
        "class Base[T, U]: pass\n" "class Child[V](Base[list[V], str]): pass\n" "type Alias[W] = Child[W]\n",
        namespace,
    )
    base, child, alias = (namespace[key] for key in ("Base", "Child", "Alias"))
    builder = ContainerBuilder()
    registration_id = builder.register(alias[int])
    target = selected(compiler_for(builder), DerivedServices(base), registration_id, alias[int])
    assert target is not None and target.projected_contract == base[list[int], str]
    assert target.bindings == dict(zip(base.__parameters__, (list[int], str), strict=True))
    assert target.requested_service_type == alias[int]


def test_finite_candidate_stream_preserves_order_and_deduplicates_by_definition_request_and_owner():
    builder = ContainerBuilder()
    group = ServiceGroup("ordered", service_type=Contract)
    first = builder.register(Contract, factory=Contract, name="first", groups=[group])
    second = builder.register(Contract, factory=Contract, name="second", groups=[group])
    compiler = compiler_for(builder)
    first_definition = compiler.blueprint.registration_definition(first)
    second_definition = compiler.blueprint.registration_definition(second)
    assert first_definition is not None and second_definition is not None
    first_registration, layer = first_definition
    second_registration, _ = second_definition
    closed = Contract[int, str]
    other_closed = Contract[bytes, str]
    specialized = compiler._specialize_factory(first_registration, layer, closed)
    alias = TypeAliasType("alias", closed)
    candidates = (
        (second_registration, layer, closed),
        (specialized, layer, closed),
        (first_registration, layer, alias),
        (first_registration, layer, other_closed),
        (second_registration, layer, closed),
    )
    expected = [(second, closed), (first, closed), (first, other_closed)]
    for selector in (group, DerivedServices(Contract)):
        for _ in range(2):
            targets = compiler._select_service_targets(selector, iter(candidates))
            assert [(target.registration_id, target.requested_service_type) for target in targets] == expected


def test_distinct_same_named_variables_across_inheritance_edges():
    parent_variable = TypeVar("Value")  # ty:ignore[mismatched-type-name]
    child_variable = TypeVar("Value")  # ty:ignore[mismatched-type-name]

    class Parent(Generic[parent_variable, U]):
        pass

    class Child(Parent[list[child_variable], child_variable], Generic[child_variable]):
        pass

    builder = ContainerBuilder()
    registration_id = builder.register(Child[int], factory=Child)
    target = selected(compiler_for(builder), DerivedServices(Parent), registration_id, Child[int])
    assert target is not None
    assert target.projected_contract == Parent[list[int], int]
    assert target.bindings == {parent_variable: list[int], U: int}
    assert child_variable not in target.bindings


def test_alias_closed_request_completes_deferred_group_constraint_at_build():
    class Service(Generic[T]):
        pass

    closed_alias = TypeAliasType("closed_alias", Service[str])
    contract_alias = TypeAliasType("contract_alias", Service[int])
    group = ServiceGroup("alias-constraint", service_type=contract_alias)
    builder = ContainerBuilder()
    builder.register(Service, groups=[group])
    builder.mark_entrypoint(closed_alias)
    with pytest.raises(ContainerBuildError, match="alias-constraint"):
        builder.build()


def test_closed_typevar_domain_constraints_and_decorator_expression_rejection():
    bounded = TypeVar("bounded", bound=int)
    constrained = TypeVar("constrained", int, str)
    assert _bind_typevar_identities(Contract[bounded, constrained], Contract[bool, str]) == {
        bounded: bool,
        constrained: str,
    }
    assert _bind_typevar_identities(Contract[bounded, constrained], Contract[str, bytes]) is None
    assert _bind_typevar_identities(Contract[T, T], Contract[int, str]) is None
    with pytest.raises(ValueError, match="Unresolved"):
        _bind_typevar_identities(Contract[T, U], Contract[int, V])


def test_deferred_open_union_and_callable_registration_expressions_close_without_name_inference():
    class Service(Generic[T]):
        pass

    for registered_arg, concrete_arg in (
        (T | int, int | str),
        (T | int, int | str | bytes),
        (TypingCallable[[T], int], TypingCallable[[str], int]),
    ):
        group = ServiceGroup("expressions", service_type=Service[concrete_arg])
        builder = ContainerBuilder()
        registration_id = builder.register(Service[registered_arg], factory=Service, groups=[group])
        compiler = compiler_for(builder)
        for selector in (group, DerivedServices(Service)):
            target = selected(compiler, selector, registration_id, Service[concrete_arg], specialize=True)
            assert target is not None and target.projected_contract == Service[concrete_arg]


def test_typing_callable_inherited_projection_rebuilds_its_parameter_list():
    class Callback(Contract[TypingCallable[[V], int], V], Generic[V]):
        pass

    group = ServiceGroup("callbacks", service_type=Contract[TypingCallable[[str], int], str])
    builder = ContainerBuilder()
    registration_id = builder.register(Callback[str], groups=[group])
    target = selected(compiler_for(builder), group, registration_id, Callback[str])
    assert target is not None
    assert target.projected_contract == Contract[TypingCallable[[str], int], str]
    builder.build()


def test_unsupported_variadic_binding_reports_the_parameter_kind():
    with pytest.raises(ValueError, match="ParamSpec"):
        _bind_typevar_identities(Callable[P, int], Callable[[str], int])  # ty:ignore[invalid-type-form]
    with pytest.raises(ValueError, match="TypeVarTuple"):
        _bind_typevar_identities(tuple[*Ts], tuple[int, str])  # ty:ignore[invalid-type-form]


def test_collapsed_union_inference_fails_explicitly():
    with pytest.raises(ValueError, match="collapsed union"):
        _bind_typevar_identities(Contract[T | int, str], Contract[int, str])


def test_unrelated_variadic_registered_contract_does_not_participate():
    class Variadic(Generic[*Ts]):
        pass

    builder = ContainerBuilder()
    registration_id = builder.register(Variadic[int], factory=Variadic)
    assert selected(compiler_for(builder), DerivedServices(Contract), registration_id, Variadic[int]) is None


def test_union_matching_does_not_fail_on_an_unused_collapsed_alternative():
    pattern = Contract[list[T | int] | list[str], U]
    concrete = Contract[list[str] | list[int | bytes], bool]
    assert _bind_typevar_identities(pattern, concrete) == {T: bytes, U: bool}


def test_closed_registration_contract_remains_authoritative_for_implementation_lookup():
    class Implementation(Contract[int, str]):
        pass

    declared = Contract[bytes, str]
    group = ServiceGroup("declared", service_type=declared)
    builder = ContainerBuilder()
    registration_id = builder.register(declared, cast(Any, Implementation), groups=[group])
    compiler = compiler_for(builder)
    for selector in (group, DerivedServices(Contract)):
        target = selected(compiler, selector, registration_id, Implementation)
        assert target is not None
        assert target.projected_contract == declared
        assert target.requested_service_type is Implementation
    builder.build()


def test_abandoned_collapsed_union_branch_does_not_poison_a_complete_match():
    pattern = list[T | int] | list[int]
    concrete = list[int] | list[bytes | int]
    assert _bind_typevar_identities(pattern, concrete) == {T: bytes}
    assert _bind_typevar_identities(Contract[pattern, T], Contract[concrete, bytes]) == {T: bytes}
    # The same tentative collapse followed by a fixed mismatch has no complete
    # candidate, so it must remain a mismatch rather than an unsupported error.
    assert _bind_typevar_identities(Contract[T | int, str], Contract[int, bytes]) is None


def test_inherited_aliases_normalize_before_diamond_projection_and_bindings():
    alias = TypeAliasType("alias", list[int])

    class Left(Contract[alias, str]):
        pass

    class Right(Contract[list[int], str]):
        pass

    class Diamond(Left, Right):  # ty:ignore[invalid-generic-class]
        pass

    group = ServiceGroup("aliased-diamond", service_type=Contract[list[int], str])
    builder = ContainerBuilder()
    registration_id = builder.register(Diamond, groups=[group])
    compiler = compiler_for(builder)
    for selector in (group, DerivedServices(Contract)):
        target = selected(compiler, selector, registration_id, Diamond)
        assert target is not None
        assert target.projected_contract == Contract[list[int], str]
        assert target.bindings == {T: list[int], U: str}
    builder.build()


def test_inherited_generic_alias_specializes_before_group_validation():
    alias_variable = TypeVar("Value")  # ty:ignore[mismatched-type-name]
    child_variable = TypeVar("Value")  # ty:ignore[mismatched-type-name]
    alias = TypeAliasType("alias", list[alias_variable], type_params=(alias_variable,))

    class Child(Contract[alias[child_variable], str], Generic[child_variable]):
        pass

    group = ServiceGroup("aliased-generic", service_type=Contract[list[int], str])
    builder = ContainerBuilder()
    registration_id = builder.register(Child[int], groups=[group])
    compiler = compiler_for(builder)
    for selector in (group, DerivedServices(Contract)):
        target = selected(compiler, selector, registration_id, Child[int])
        assert target is not None
        assert target.projected_contract == Contract[list[int], str]
        assert target.bindings == {T: list[int], U: str}
    builder.build()


def test_union_collapse_with_remaining_union_reports_unsupported_without_hiding_fixed_mismatch():
    with pytest.raises(ValueError, match="collapsed union"):
        _bind_typevar_identities(T | int | str, int | str)
    assert _bind_typevar_identities(T | int | bytes, int | str) is None
    assert _bind_typevar_identities(list[T] | int | str, int | str) is None

    builder = ContainerBuilder()
    registration_id = builder.register(Contract[int | str, bool], factory=Contract)
    compiler = compiler_for(builder)
    with pytest.raises(ContainerBuildError, match="collapsed union") as error:
        selected(compiler, DerivedServices(Contract[T | int | str, bool]), registration_id, Contract[int | str, bool])
    assert error.value.code == "service-target-projection"
    assert (
        selected(compiler, DerivedServices(Contract[T | int | bytes, bool]), registration_id, Contract[int | str, bool])
        is None
    )


def test_cached_projection_keeps_group_layer_request_and_compiler_identity(monkeypatch):
    from dataclasses import replace

    import clean_ioc.container as implementation

    group = ServiceGroup("same-name", service_type=Contract)
    other_group = ServiceGroup("same-name", service_type=Contract)
    builder = ContainerBuilder()
    registration_id = builder.register(Contract, factory=Contract, groups=[group])
    compiler = compiler_for(builder)
    registration, layer = compiler.blueprint.registration_definition(registration_id)
    other_layer = replace(layer, service_groups={registration_id: frozenset({other_group})})
    calls = []
    original = implementation._select_service_target

    def project(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(implementation, "_select_service_target", project)
    first = compiler._select_service_target(group, registration, layer, Contract[int, str])
    assert first is not None and first.bindings == {T: int, U: str}
    assert compiler._select_service_target(group, registration, layer, Contract[int, str]) is first
    assert len(calls) == 1
    assert compiler._select_service_target(other_group, registration, layer, Contract[int, str]) is None
    assert compiler._select_service_target(other_group, registration, layer, Contract[int, str]) is None
    assert len(calls) == 2  # Negative results are reusable too.
    assert compiler._select_service_target(group, registration, other_layer, Contract[int, str]) is None
    assert compiler._select_service_target(other_group, registration, other_layer, Contract[int, str]) is not None
    second = compiler._select_service_target(group, registration, layer, Contract[bytes, bool])
    assert second is not None and second.bindings == {T: bytes, U: bool}
    compiler._area = "another-visible-area"
    assert compiler._select_service_target(group, registration, layer, Contract[int, str]) == first
    assert len(calls) == 6
    assert selected(compiler_for(builder), group, registration_id, Contract[int, str]) == first
    assert len(calls) == 7


def test_cached_projection_does_not_merge_same_named_selector_typevars():
    first = TypeVar("Same")  # ty: ignore[mismatched-type-name]
    second = TypeVar("Same")  # ty: ignore[mismatched-type-name]
    builder = ContainerBuilder()
    registration_id = builder.register(Contract[int, str], factory=Contract)
    compiler = compiler_for(builder)
    for variable in (first, second, first):
        target = selected(compiler, DerivedServices(Contract[variable, str]), registration_id, Contract[int, str])
        assert target is not None
        assert target.declaration_bindings == {variable: int}


def test_template_labels_do_not_hash_user_metadata_and_are_compiler_local(monkeypatch):
    import clean_ioc.container as implementation

    class Unhashable:
        __hash__ = None

    value = Unhashable()
    calls = []

    def label(item):
        calls.append(item)
        return "captured label"

    monkeypatch.setattr(implementation, "qualified_name", label)
    compiler = compiler_for(ContainerBuilder())
    assert compiler._template_label(value) == "captured label"
    assert compiler._template_label(value) == "captured label"
    assert calls == [value]
    assert compiler_for(ContainerBuilder())._template_label(value) == "captured label"
    assert calls == [value, value]
