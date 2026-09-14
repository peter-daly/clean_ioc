from unittest.mock import Mock

from assertive import was_called, was_called_once, was_called_once_with, was_not_called

from clean_ioc import ComponentBuilder, ContainerBuilder
from clean_ioc.bundles import (
    BaseBundle,
    OnlyRunOncePerClassBundle,
    OnlyRunOncePerInstanceBundle,
    RunOnceBundle,
)


def test_only_run_once_per_instance_bundle_will_only_run_once_per_instance():
    spy = Mock()

    class TestBundle(OnlyRunOncePerInstanceBundle):
        def __init__(self, mock):
            self.mock = mock

        def apply(self, builder: ComponentBuilder):
            self.mock()

    container = ContainerBuilder()
    test_bundle = TestBundle(spy)

    container.apply_bundle(test_bundle)
    container.apply_bundle(test_bundle)
    container.apply_bundle(test_bundle)

    assert spy == was_called_once()


def test_bundle_instance_can_be_called_multiple_times_when_allowed():
    spy = Mock()

    class TestBundle(BaseBundle):
        def __init__(self, mock):
            self.mock = mock

        def apply(self, builder: ComponentBuilder):
            self.mock()

    container = ContainerBuilder()
    test_bundle = TestBundle(spy)

    container.apply_bundle(test_bundle)
    container.apply_bundle(test_bundle)
    container.apply_bundle(test_bundle)

    assert spy == was_called().times(3)


def test_bundle_can_apply_a_nested_bundle_through_component_builder_protocol():
    class Dependency:
        pass

    class DependencyBundle(BaseBundle):
        def apply(self, builder: ComponentBuilder):
            builder.register(Dependency)

    class ApplicationBundle(BaseBundle):
        def apply(self, builder: ComponentBuilder):
            builder.apply_bundle(DependencyBundle())

    builder = ContainerBuilder()
    builder.apply_bundle(ApplicationBundle())

    assert isinstance(builder.build().resolve(Dependency), Dependency)


def test_bundle_class_can_be_called_multiple_times_with_different_instances():
    spy1 = Mock()
    spy2 = Mock()

    class TestBundle(OnlyRunOncePerInstanceBundle):
        def __init__(self, mock):
            self.mock = mock

        def apply(self, builder: ComponentBuilder):
            self.mock()

    container = ContainerBuilder()
    test_bundle1 = TestBundle(spy1)
    test_bundle2 = TestBundle(spy2)

    container.apply_bundle(test_bundle1)
    container.apply_bundle(test_bundle2)
    container.apply_bundle(test_bundle1)
    container.apply_bundle(test_bundle2)

    assert spy1 == was_called_once()
    assert spy2 == was_called_once()


def test_bundle_class_same_instance_can_run_on_multiple_containers():
    spy = Mock()

    class TestBundle(OnlyRunOncePerInstanceBundle):
        def __init__(self, mock):
            self.mock = mock

        def apply(self, builder: ComponentBuilder):
            self.mock(builder)

    container1 = ContainerBuilder()
    container2 = ContainerBuilder()
    test_bundle = TestBundle(spy)

    container1.apply_bundle(test_bundle)
    container2.apply_bundle(test_bundle)
    container1.apply_bundle(test_bundle)

    assert spy == was_called_once_with(container1)
    assert spy == was_called_once_with(container2)
    assert spy == was_called().twice()


def test_bundle_class_can_be_called_only_once_across_all_instances_when_set():
    spy1 = Mock()
    spy2 = Mock()

    class TestBundle(OnlyRunOncePerClassBundle):
        def __init__(self, mock):
            self.mock = mock

        def apply(self, builder: ComponentBuilder):
            self.mock()

    container = ContainerBuilder()
    test_bundle1 = TestBundle(spy1)
    test_bundle2 = TestBundle(spy2)

    container.apply_bundle(test_bundle1)
    container.apply_bundle(test_bundle2)
    container.apply_bundle(test_bundle1)
    container.apply_bundle(test_bundle2)

    assert spy1 == was_called_once()
    assert spy2 == was_not_called()


def test_custom_run_once_bundle():
    spy1 = Mock()
    spy2 = Mock()
    spy3 = Mock()

    class TestBundle(RunOnceBundle):
        def __init__(self, name: str, mock):
            self.name = name
            self.mock = mock

        def get_bundle_identifier(self) -> str:
            return f"{self.__class__.__name__}-{self.name}"

        def apply(self, builder: ComponentBuilder):
            self.mock()

    container = ContainerBuilder()
    test_bundle1 = TestBundle("ME", spy1)
    test_bundle2 = TestBundle("YOU", spy2)
    test_bundle3 = TestBundle("ME", spy3)

    container.apply_bundle(test_bundle1)
    container.apply_bundle(test_bundle2)
    container.apply_bundle(test_bundle3)

    assert spy1 == was_called_once()
    assert spy2 == was_called_once()
    assert spy3 == was_not_called()
