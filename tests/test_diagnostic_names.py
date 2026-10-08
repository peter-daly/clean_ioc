import gc
import sys
import weakref
from enum import Enum
from types import GenericAlias
from typing import Callable, Generic, Literal, NewType, TypeVar, Union, cast

import pytest
from typing_extensions import TypeAliasType

from clean_ioc import CompilationBudget, CompilationProfiler, ContainerBuilder, ContainerBuildError, Provider
from clean_ioc.tooling import _DiagnosticNames, qualified_name

Item = TypeVar("Item")
Nominal = NewType("Nominal", int)
Alias = TypeAliasType("Alias", list[int])
GenericAliasDeclaration = TypeAliasType("GenericAliasDeclaration", list[Item], type_params=(Item,))


class Colour(Enum):
    red = "red"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "None"),
        (type(None), "None"),
        (Item, "TypeVar(Item)"),
        (list[dict[str, tuple[int, ...]]], "list[dict[str, tuple[int, builtins.ellipsis]]]"),
        (Union[str, int, None], "typing.Union[None, int, str]"),
        (str | int, "typing.Union[int, str]"),
        (Literal["alpha", 2, True, None, b"x"], "typing.Literal[alpha, 2, True, None, b'x']"),
        (Literal[Colour.red], f"typing.Literal[{__name__}.Colour.red]"),
        (Nominal, f"{__name__}.Nominal"),
        (Alias, f"{__name__}.Alias"),
    ],
)
def test_compilation_names_preserve_public_diagnostic_spelling(value, expected):
    names = _DiagnosticNames()
    assert names(value) == qualified_name(value) == expected
    assert names(value) is names(value)


def test_alias_application_keeps_existing_spelling_and_does_not_expand_its_value():
    application = GenericAliasDeclaration[list[int]]
    names = _DiagnosticNames()
    # Alias labels intentionally use the existing alias-label grammar: unlike
    # ordinary generic names, a nested built-in application spells its origin.
    assert names(application) == qualified_name(application) == f"{__name__}.GenericAliasDeclaration[list]"
    assert names(Callable[[int], str]) == qualified_name(Callable[[int], str])


def test_recursive_generic_rendering_reuses_child_names_and_deduplicates_equal_strings(monkeypatch):
    import clean_ioc.tooling as tooling

    rendered = []
    original = tooling._render_qualified_name

    def record(value, name):
        rendered.append(value)
        return original(value, name)

    monkeypatch.setattr(tooling, "_render_qualified_name", record)
    names = _DiagnosticNames()
    child = GenericAlias(dict, (str, int))
    first = GenericAlias(list, child)
    second = GenericAlias(list, child)
    assert first is not second
    assert names(first) is names(second)
    assert names(child) == "dict[str, int]"
    assert sum(value is child for value in rendered) == 1
    assert sum(value is dict for value in rendered) == 1
    assert sum(value is int for value in rendered) == 1


def test_diagnostic_cache_never_hashes_compares_or_represents_unsupported_values():
    class Hostile:
        def fail(self, *args):
            raise AssertionError("User callback must not run")

        __repr__ = __str__ = __hash__ = __eq__ = fail

    class HostileString(str):
        def fail(self, *args):
            raise AssertionError("String callback must not run")

        __hash__ = __eq__ = fail

    names = _DiagnosticNames()
    first, second = Hostile(), Hostile()
    assert names(first) is names(second)
    assert names(first) == qualified_name(first)
    literal = GenericAlias(cast(type, Literal), (first,))
    assert names(literal) == f"typing.Literal[{qualified_name(first)}]"
    # Even unusual class metadata must not become user-authored dictionary keys.
    declaration = type("Declaration", (), {})
    declaration.__module__ = "builtins"
    declaration.__qualname__ = HostileString("Declaration")
    assert names(declaration).__class__ is str
    assert names(declaration) == "Declaration"


def test_builds_and_failed_build_retries_refresh_metadata_and_public_names_stay_live():
    class Missing:
        pass

    class Root:
        def __init__(self, missing: Missing):
            self.missing = missing

    builder = ContainerBuilder()
    builder.register(Root)
    old_label = qualified_name(Root)
    with pytest.raises(ContainerBuildError) as failed:
        builder.build(diagnostics=True)
    assert failed.value.report is not None
    assert any(old_label in issue.path for issue in failed.value.report.issues)
    Root.__qualname__ = "RenamedRoot"
    new_label = qualified_name(Root)
    assert new_label == f"{__name__}.RenamedRoot"
    builder.register(Missing, root_policy="dependency_only")
    with builder.build(diagnostics=True) as owner:
        explanation = next(item for item in owner._plan.occurrence_explanations.values() if item.subject == new_label)
        assert new_label in explanation.path
        Root.__qualname__ = "OverlayRoot"
        assert qualified_name(Root) == f"{__name__}.OverlayRoot"
        with owner.new_scope_builder().build(diagnostics=True) as overlay:
            assert any(item.subject == qualified_name(Root) for item in overlay._plan.occurrence_explanations.values())


def test_reentrant_builds_get_independent_snapshots():
    class Shared:
        pass

    nested_subjects = []
    prior_label = qualified_name(Shared)

    def selection(component):
        Shared.__qualname__ = "NestedShared"
        nested = ContainerBuilder()
        nested.register(Shared)
        with nested.build(diagnostics=True) as owner:
            nested_subjects.extend(item.subject for item in owner._plan.occurrence_explanations.values())
        return True

    outer = ContainerBuilder()
    outer.register(Shared, when=selection)
    with outer.build(diagnostics=True) as owner:
        assert any(item.subject == prior_label for item in owner._plan.occurrence_explanations.values())
        assert f"{__name__}.NestedShared" in nested_subjects
    fresh = ContainerBuilder()
    fresh.register(Shared)
    with fresh.build(diagnostics=True) as owner:
        assert any(item.subject == qualified_name(Shared) for item in owner._plan.occurrence_explanations.values())


@pytest.mark.parametrize("instrumented", [False, True])
def test_frozen_plan_retains_shared_strings_but_no_compiler_name_cache(monkeypatch, instrumented):
    caches = []
    original = _DiagnosticNames.__init__

    def capture(self):
        original(self)
        caches.append(weakref.ref(self))

    monkeypatch.setattr(_DiagnosticNames, "__init__", capture)

    class Shared(Generic[Item]):
        pass

    class First:
        def __init__(self, shared: Shared[list[int]]):
            self.shared = shared

    class Second:
        def __init__(self, shared: Shared[list[int]]):
            self.shared = shared

    builder = ContainerBuilder()
    builder.register(Shared[list[int]], root_policy="dependency_only")
    builder.register(First)
    builder.register(Second)
    kwargs = {"budget": CompilationBudget(), "profile": CompilationProfiler(max_records=0)} if instrumented else {}
    with builder.build(**kwargs, diagnostics=True) as owner:
        gc.collect()
        assert caches and all(reference() is None for reference in caches)
        label = qualified_name(Shared[list[int]])
        subjects = [
            name
            for explanation in owner._plan.occurrence_explanations.values()
            for name in explanation.path
            if name == label
        ]
        annotations = [
            parameter.canonical_annotation
            for records in owner._plan.parameter_explanations.values()
            for parameter in records.values()
            if parameter.canonical_annotation == label
        ]
        assert len(subjects) >= 2 and len(annotations) >= 2
        assert len({id(value) for value in (*subjects, *annotations)}) == 1
        assert isinstance(owner.resolve(Provider[First])().shared, Shared)


def test_sources_are_kept_only_until_compiler_cache_is_released():
    names = _DiagnosticNames()
    source = type("Ephemeral", (), {})
    reference = weakref.ref(source)
    label = names(source)
    del source
    gc.collect()
    assert reference() is not None  # Prevent id recycling during compilation.
    del names
    gc.collect()
    assert reference() is None
    assert label.endswith("Ephemeral")


def test_name_reuse_reduces_actual_retained_string_storage():
    value = Provider[dict[str, tuple[list[int], ...]]]
    names = _DiagnosticNames()
    uncached = [qualified_name(value) for _ in range(2000)]
    cached = [names(value) for _ in range(2000)]
    uncached_bytes = sum(sys.getsizeof(label) for label in {id(label): label for label in uncached}.values())
    cached_bytes = sum(sys.getsizeof(label) for label in {id(label): label for label in cached}.values())
    assert uncached == cached
    assert cached_bytes * 1000 < uncached_bytes
