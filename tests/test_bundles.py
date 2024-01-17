from unittest.mock import Mock
from clean_ioc import Container
from clean_ioc.bundles import (
    OnlyRunOncePerClassBundle,
    OnlyRunOncePerInstanceBundle,
    BaseBundle,
)
from assertive import assert_that, was_called


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
        INSTANCE_RUN_ONCE = False

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
