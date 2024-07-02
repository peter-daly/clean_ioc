from unittest.mock import Mock

from assertive import assert_that, was_called, was_called_with

from clean_ioc import Container
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

        def apply(self, container: Container):
            self.mock()

    container = Container()
    test_bundle = TestBundle(spy)

    container.apply_bundle(test_bundle)
    container.apply_bundle(test_bundle)
    container.apply_bundle(test_bundle)

    assert_that(spy).matches(was_called().once)


def test_bundle_instance_can_be_called_multiple_times_when_allowed():
    spy = Mock()

    class TestBundle(BaseBundle):
        def __init__(self, mock):
            self.mock = mock

        def apply(self, container: Container):
            self.mock()

    container = Container()
    test_bundle = TestBundle(spy)

    container.apply_bundle(test_bundle)
    container.apply_bundle(test_bundle)
    container.apply_bundle(test_bundle)

    assert_that(spy).matches(was_called().times(3))


def test_bundle_class_can_be_called_multiple_times_with_different_instances():
    spy1 = Mock()
    spy2 = Mock()

    class TestBundle(OnlyRunOncePerInstanceBundle):
        def __init__(self, mock):
            self.mock = mock

        def apply(self, container: Container):
            self.mock()

    container = Container()
    test_bundle1 = TestBundle(spy1)
    test_bundle2 = TestBundle(spy2)

    container.apply_bundle(test_bundle1)
    container.apply_bundle(test_bundle2)
    container.apply_bundle(test_bundle1)
    container.apply_bundle(test_bundle2)

    assert_that(spy1).matches(was_called().once)
    assert_that(spy2).matches(was_called().once)


def test_bundle_class_same_instance_can_run_on_multiple_containers():
    spy = Mock()

    class TestBundle(OnlyRunOncePerInstanceBundle):
        def __init__(self, mock):
            self.mock = mock

        def apply(self, container: Container):
            self.mock(container)

    container1 = Container()
    container2 = Container()
    test_bundle = TestBundle(spy)

    container1.apply_bundle(test_bundle)
    container2.apply_bundle(test_bundle)
    container1.apply_bundle(test_bundle)

    assert_that(spy).matches(was_called_with(container1).once)
    assert_that(spy).matches(was_called_with(container2).once)
    assert_that(spy).matches(was_called().twice)


def test_bundle_class_can_be_called_only_once_across_all_instances_when_set():
    spy1 = Mock()
    spy2 = Mock()

    class TestBundle(OnlyRunOncePerClassBundle):
        def __init__(self, mock):
            self.mock = mock

        def apply(self, container: Container):
            self.mock()

    container = Container()
    test_bundle1 = TestBundle(spy1)
    test_bundle2 = TestBundle(spy2)

    container.apply_bundle(test_bundle1)
    container.apply_bundle(test_bundle2)
    container.apply_bundle(test_bundle1)
    container.apply_bundle(test_bundle2)

    assert_that(spy1).matches(was_called().once)
    assert_that(spy2).matches(was_called().never)


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

        def apply(self, container: Container):
            self.mock()

    container = Container()
    test_bundle1 = TestBundle("ME", spy1)
    test_bundle2 = TestBundle("YOU", spy2)
    test_bundle3 = TestBundle("ME", spy3)

    container.apply_bundle(test_bundle1)
    container.apply_bundle(test_bundle2)
    container.apply_bundle(test_bundle3)

    assert_that(spy1).matches(was_called().once)
    assert_that(spy2).matches(was_called().once)
    assert_that(spy3).matches(was_called().never)
