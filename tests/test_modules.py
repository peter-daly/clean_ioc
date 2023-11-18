from unittest.mock import Mock
from clean_ioc import Container
from clean_ioc.modules import BaseModule
from fluent_assertions import assert_that, was_called


def test_module_will_only_run_once_per_instance():
    spy = Mock()

    class TestModule(BaseModule):
        def __init__(self, mock):
            self.mock = mock

        def run(self, container: Container):
            self.mock()

    container = Container()
    test_module = TestModule(spy)

    container.apply_module(test_module)
    container.apply_module(test_module)
    container.apply_module(test_module)

    assert_that(spy).matches(was_called().once)


def test_module_instance_can_be_called_multiple_times_when_allowed():
    spy = Mock()

    class TestModule(BaseModule):
        INSTANCE_RUN_ONCE = False

        def __init__(self, mock):
            self.mock = mock

        def run(self, container: Container):
            self.mock()

    container = Container()
    test_module = TestModule(spy)

    container.apply_module(test_module)
    container.apply_module(test_module)
    container.apply_module(test_module)

    assert_that(spy).matches(was_called().times(3))


def test_module_class_can_be_called_multiple_times_with_different_instances():
    spy1 = Mock()
    spy2 = Mock()

    class TestModule(BaseModule):
        def __init__(self, mock):
            self.mock = mock

        def run(self, container: Container):
            self.mock()

    container = Container()
    test_module1 = TestModule(spy1)
    test_module2 = TestModule(spy2)

    container.apply_module(test_module1)
    container.apply_module(test_module2)
    container.apply_module(test_module1)
    container.apply_module(test_module2)

    assert_that(spy1).matches(was_called().once)
    assert_that(spy2).matches(was_called().once)


def test_module_class_can_be_called_only_once_across_all_instances_when_set():
    spy1 = Mock()
    spy2 = Mock()

    class TestModule(BaseModule):
        CLASS_RUN_ONCE = True

        def __init__(self, mock):
            self.mock = mock

        def run(self, container: Container):
            self.mock()

    container = Container()
    test_module1 = TestModule(spy1)
    test_module2 = TestModule(spy2)

    container.apply_module(test_module1)
    container.apply_module(test_module2)
    container.apply_module(test_module1)
    container.apply_module(test_module2)

    assert_that(spy1).matches(was_called().once)
    assert_that(spy2).matches(was_called().never)
