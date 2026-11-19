"""Execution instructions have fixed storage and remain weakly referenceable."""

import gc
import weakref

import pytest

from clean_ioc import ContainerBuilder, Instrumentation, ResolutionProfiler
from clean_ioc import container as code


@pytest.mark.parametrize(
    "step_type",
    [value for value in vars(code).values() if isinstance(value, type) and issubclass(value, code._Step)],
    ids=lambda value: value.__name__,
)
def test_execution_step_types_do_not_inherit_instance_dictionaries(step_type):
    # Check every concrete instruction, including the observed multiple-inheritance
    # variants: one unslotted base silently adds a dictionary to all its descendants.
    step = object.__new__(step_type)
    assert not hasattr(step, "__dict__")
    assert weakref.ref(step)() is step


@pytest.mark.parametrize("lifespan", ["transient", "per_resolution", "scoped", "singleton"])
@pytest.mark.parametrize("observed", [False, True])
def test_compiled_steps_resolve_and_release_after_the_runtime_is_discarded(lifespan, observed):
    class Service:
        def __init__(self, value: int):
            self.value = value

    builder = ContainerBuilder().set_provider_roots(())
    builder.register(Service, arguments={"value": 42}, lifespan=lifespan)
    profiler = ResolutionProfiler()
    with builder.build(instrumentation=Instrumentation(profiler) if observed else None) as runtime:
        step = runtime._plan.default_roots[Service].step
        assert not hasattr(step, "__dict__")
        reference = weakref.ref(step)
        assert runtime.resolve(Service).value == 42
        if observed:
            assert any(record.kind == "registration" and record.completed == 1 for record in profiler.report().records)
    del step, runtime
    gc.collect()
    assert reference() is None
