"""The public verification findings and runtime ownership contracts."""

import asyncio
import gc
import json
import subprocess
import sys
import weakref
from contextlib import asynccontextmanager, contextmanager
from dataclasses import FrozenInstanceError
from itertools import count

import pytest

import clean_ioc
from clean_ioc import (
    BuildIssue,
    ContainerBuilder,
    Instrumentation,
    IssueSeverity,
    Provider,
    ProviderScopeClosedError,
    ResolutionProfiler,
    ScopeBuilder,
    VerificationReport,
    VerificationRuntimeUnavailableError,
)


def test_public_api_has_one_direct_report_without_legacy_aliases():
    for name in ("AnalysisResult", "AnalysisReport", "AnalysisRuntimeUnavailableError"):
        assert not hasattr(clean_ioc, name)
    for builder in (ContainerBuilder, ScopeBuilder):
        assert not hasattr(builder, "analyse")
        assert hasattr(builder, "verify")
    with ContainerBuilder().verify() as report:
        assert isinstance(report, VerificationReport)
        assert not hasattr(report, "report")
        report.assert_valid()
        assert report.is_valid and report.complete and report.emission_complete


def test_findings_stay_frozen_and_readable_after_runtime_ownership_closes():
    calls = []
    builder = ContainerBuilder()
    builder.add_validation_rule(
        lambda _: calls.append("rule") or [BuildIssue("notice", IssueSeverity.warning, "Notice")]
    )
    report = builder.verify()
    before = report.to_json()
    first = report.create_runtime()
    second = report.create_runtime()
    assert first is not second
    with pytest.raises(FrozenInstanceError):
        report.complete = False  # ty: ignore[invalid-assignment]
    report.close()
    assert first._closed and second._closed
    assert report.to_json() == before
    assert report.assert_valid() is None
    assert report.warnings and not report.errors
    assert calls == ["rule"]
    with pytest.raises(RuntimeError, match="closed"):
        report.create_runtime()


@pytest.mark.parametrize("observed", [False, True])
def test_report_keeps_open_runtimes_and_releases_closed_ones(observed):
    class Resource:
        pass

    serials = count()
    cleaned = []

    @contextmanager
    def acquire():
        serial = next(serials)
        try:
            yield Resource()
        finally:
            cleaned.append(serial)

    builder = ContainerBuilder().set_provider_roots(())
    builder.register(Resource, factory=acquire, lifespan="singleton")
    instrumentation = Instrumentation(ResolutionProfiler(sample_durations=0)) if observed else None
    with builder.verify() as report:

        def start(*, close=False):
            runtime = report.create_runtime(instrumentation=instrumentation)
            value = runtime.resolve(Resource)
            if close:
                runtime.__exit__()
            return weakref.ref(runtime), weakref.ref(value)

        first = start()
        closed = start(close=True)
        last = start()
        gc.collect()
        assert all(ref() is None for ref in closed)
        assert all(ref() is not None for ref in (*first, *last))
        assert cleaned == [1]

        report.close()
        gc.collect()
        assert all(ref() is None for ref in (*first, *last))
    assert cleaned == [1, 2, 0]
    if instrumentation is not None:
        cleanups = [record for record in instrumentation.profiler.report().records if record.path == "<owner cleanup>"]
        assert [(record.attempts, record.completed) for record in cleanups] == [(1, 1)] * 3


def test_externally_retained_runtime_does_not_keep_its_report_or_siblings_alive():
    report = ContainerBuilder().verify()
    report_ref = weakref.ref(report)
    with report.create_runtime():
        sibling_ref = weakref.ref(report.create_runtime())
        del report
        gc.collect()
        assert report_ref() is None and sibling_ref() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("retained", ["child", "provider"])
async def test_closed_overlay_remains_alive_through_its_child_or_provider(retained):
    class Singleton:
        pass

    class Transient:
        pass

    parent_builder = ContainerBuilder()
    composition = parent_builder.retain_composition()
    with parent_builder.build() as parent:
        builder = ScopeBuilder(parent, composition=composition)
        builder.register(Singleton, lifespan="singleton")
        builder.register(Transient, lifespan="transient")
        async with builder.verify() as report:
            async with report.create_runtime() as runtime:
                runtime_ref = weakref.ref(runtime)
                value_ref = weakref.ref(runtime.resolve(Singleton))
                provider = runtime.resolve(Provider[Transient])
                child = runtime.new_scope()
            del runtime

            with pytest.raises(ProviderScopeClosedError):
                provider()
            with child:
                assert isinstance(child.resolve(Transient), Transient)
            if retained == "child":
                del provider
            else:
                del child
            gc.collect()
            assert runtime_ref() is not None and value_ref() is not None
            if retained == "child":
                del child
            else:
                del provider
            gc.collect()
            assert runtime_ref() is None and value_ref() is None


def test_failed_runtime_cleanup_releases_ownership_after_reentrant_close():
    class Resource:
        pass

    cleaned = []
    runtime_ref = None

    @contextmanager
    def acquire():
        yield Resource()
        assert runtime_ref is not None
        runtime = runtime_ref()
        assert runtime is not None
        runtime.__exit__()
        cleaned.append("resource")
        raise ValueError("cleanup failed")

    builder = ContainerBuilder().set_provider_roots(())
    builder.register(Resource, factory=acquire, lifespan="singleton")
    with builder.verify() as report:
        runtime = report.create_runtime()
        runtime_ref = weakref.ref(runtime)
        value_ref = weakref.ref(runtime.resolve(Resource))
        with pytest.raises(ValueError, match="cleanup failed"):
            runtime.__exit__()
        runtime.__exit__()
        del runtime
        gc.collect()
        assert runtime_ref() is None and value_ref() is None
    assert cleaned == ["resource"]


@pytest.mark.asyncio
async def test_overlapping_report_closes_preserve_pending_cleanup_and_cancellation(monkeypatch):
    class Resource:
        name = ""

    cleaned = []
    awaiting_cleanup = asyncio.Event()
    finish_cleanup = asyncio.Event()

    @asynccontextmanager
    async def acquire():
        resource = Resource()
        try:
            yield resource
        finally:
            try:
                if resource.name == "awaiting":
                    awaiting_cleanup.set()
                    await finish_cleanup.wait()
            finally:
                cleaned.append(resource.name)

    builder = ContainerBuilder().set_provider_roots(())
    builder.register(Resource, factory=acquire, lifespan="singleton")
    report = builder.verify()
    first, middle, last = (report.create_runtime() for _ in range(3))
    for runtime, name in ((first, "first"), (middle, "middle"), (last, "awaiting")):
        (await runtime.resolve_async(Resource)).name = name
    del runtime

    # Observe close attempts without extending runtime lifetimes.
    attempts = []
    original_exit = type(last).__aexit__

    async def record_exit(runtime, *args):
        attempts.append(id(runtime))
        return await original_exit(runtime, *args)

    monkeypatch.setattr(type(last), "__aexit__", record_exit)
    first_id, middle_id, last_id = id(first), id(middle), id(last)
    middle_ref = weakref.ref(middle)
    del first
    closing = asyncio.create_task(report.aclose())
    try:
        await asyncio.wait_for(awaiting_cleanup.wait(), timeout=5)
        await middle.__aexit__()
        del middle
        gc.collect()
        assert middle_ref() is None
        await last.__aexit__()
        await asyncio.wait_for(report.aclose(), timeout=5)
        assert attempts == [last_id, middle_id, last_id, last_id, first_id]
        assert cleaned == ["middle", "first"]
        await asyncio.wait_for(report.aclose(), timeout=5)
        assert attempts[-1] == last_id
        assert len(attempts) == 6
        assert not closing.done()
    finally:
        closing.cancel("teardown interrupted")
        with pytest.raises(asyncio.CancelledError, match="teardown interrupted"):
            await closing

    await report.aclose()
    assert len(attempts) == 6
    assert cleaned == ["middle", "first", "awaiting"]


def test_manually_constructed_valid_findings_have_no_execution_plan():
    report = VerificationReport()
    report.assert_valid()
    assert report.is_valid and not report.emission_complete
    assert report.selected_registrations is None
    with pytest.raises(VerificationRuntimeUnavailableError) as caught:
        report.create_runtime()
    assert caught.value.report is report


def test_direct_builder_assertion_remains_active_under_optimized_python():
    source = """
from clean_ioc import BuildIssue, ContainerBuilder, IssueSeverity
builder = ContainerBuilder()
builder.add_validation_rule(lambda _: [BuildIssue('required', IssueSeverity.error, 'Required')])
report = builder.verify()
try:
    report.assert_valid()
except AssertionError as error:
    print(error)
else:
    raise RuntimeError('Verification assertion was disabled')
"""
    command = [sys.executable, "-O", "-c", source]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)  # noqa: S603
    result = json.loads(completed.stdout)["runs"][0]["results"][0]
    assert result["ruleId"] == "required"
