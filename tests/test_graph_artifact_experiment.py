"""Contract checks for the local prototype, not a public persistence API."""

import gc
import json
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks import graph_artifact_fixture as fixture
from benchmarks.graph_artifact import dump_graph, load_graph
from clean_ioc import ContainerBuilder, _legacy, container


def _build(builder):
    return builder.build(
        diagnostics=False,
        provider_roots=(),
        allow_scope_builders=False,
        check_unreachable=False,
        aggregate_errors=False,
    )


@pytest.mark.parametrize("lifespan", ["transient", "per_resolution", "scoped", "singleton"])
async def test_lifetime_and_identity_survive_roundtrip(tmp_path, monkeypatch, lifespan):
    builder = ContainerBuilder()
    builder.register(fixture.Leaf, lifespan=lifespan, root_policy="dependency_only")
    builder.register(fixture.Pair, lifespan="transient")
    original = _build(builder)
    artifact = tmp_path / "graph.jsonl"
    dump_graph(original, artifact)

    def forbidden(*args, **kwargs):
        raise AssertionError("Loading must not build or inspect constructors")

    monkeypatch.setattr(ContainerBuilder, "build", forbidden)
    monkeypatch.setattr(container._Compiler, "__init__", forbidden)
    monkeypatch.setattr(_legacy, "_set_up_dependencies", forbidden)
    monkeypatch.setattr(_legacy._Registration, "__init__", forbidden)
    monkeypatch.setattr(fixture, "ACTIVATIONS", 0)
    with load_graph(artifact) as loaded:
        assert fixture.ACTIVATIONS == 0
        assert loaded.graph.manifest(all_roots=True).to_dict() == original.graph.manifest(all_roots=True).to_dict()
        plan = loaded._plan
        root = plan.default_roots[fixture.Pair]
        assert root is plan.roots[fixture.Pair][0]
        assert root.component._graph is plan.graph
        assert isinstance(root.step, container._RegistrationStep)
        assert root.step.component._graph is plan.graph
        dependencies = root.step.dependencies
        assert isinstance(dependencies[0].step, container._RegistrationStep)
        assert isinstance(dependencies[1].step, container._RegistrationStep)
        assert dependencies[0].step.registration is dependencies[1].step.registration
        with loaded.new_scope() as first_scope, loaded.new_scope() as second_scope:
            first = first_scope.resolve(fixture.Pair)
            repeated = await first_scope.resolve_async(fixture.Pair)
            second = second_scope.resolve(fixture.Pair)
            assert (first.left is first.right) == (lifespan != "transient")
            assert (first.left is repeated.left) == (lifespan in ("scoped", "singleton"))
            assert (first.left is second.left) == (lifespan == "singleton")
            assert first is not repeated


def test_large_topology_and_runtime_instances(tmp_path):
    original = fixture.build(4)
    artifact = tmp_path / "graph.jsonl"
    dump_graph(original, artifact)
    with load_graph(artifact) as loaded:
        assert len(loaded._plan.graph._records or ()) == 1024
        records = loaded._plan.graph._records
        assert records is not None
        occurrence_id = max(records)
        assert occurrence_id is records[occurrence_id].occurrence_id
        graph = loaded.graph
        assert isinstance(graph._occurrence_layers, container._OccurrenceLayers)
        origins = gc.get_referents(graph._occurrence_origins)[0]
        assert origins is gc.get_referents(graph._occurrence_layers.origins)[0]
        instances = [loaded.resolve(root) for root in fixture.ROOTS[:4]]
        assert fixture.inspect_instances(instances) == {"objects": 1024, "leaves": 512, "payload_bytes": 65536}


def test_rejects_instances_and_already_resolved_containers(tmp_path):
    builder = ContainerBuilder()
    builder.register(fixture.Leaf, instance=fixture.Leaf())
    with pytest.raises(ValueError, match="instances"):
        dump_graph(_build(builder), tmp_path / "instance.jsonl")
    built = fixture.build(1)
    built.resolve(fixture.ROOTS[0])
    with pytest.raises(ValueError, match="before resolving"):
        dump_graph(built, tmp_path / "resolved.jsonl")


def test_rejects_local_classes_without_publishing_partial_artifact(tmp_path):
    class Local:
        pass

    builder = ContainerBuilder()
    builder.register(Local)
    artifact = tmp_path / "graph.jsonl"
    with pytest.raises(ValueError, match="importable"):
        dump_graph(_build(builder), artifact)
    assert not artifact.exists()
    assert not list(tmp_path.iterdir())


def test_rejects_incompatible_and_incomplete_artifacts(tmp_path):
    artifact = tmp_path / "graph.jsonl"
    dump_graph(fixture.build(1), artifact)
    lines = artifact.read_text().splitlines()
    header = json.loads(lines[0])
    header["compatibility"]["schema"] += 1
    artifact.write_text(json.dumps(header) + "\n" + "\n".join(lines[1:]))
    with pytest.raises(ValueError, match="does not match"):
        load_graph(artifact)
    artifact.write_text("\n".join(lines[:-1]) + "\n")
    with pytest.raises(ValueError, match="Incomplete artifact"):
        load_graph(artifact)
    artifact.write_text(lines[0] + '\n[0,"tuple",[[20]]]\n')
    with pytest.raises(ValueError, match="Invalid artifact reference"):
        load_graph(artifact)


def test_rejects_changed_imported_module(tmp_path):
    artifact = tmp_path / "graph.jsonl"
    dump_graph(fixture.build(1), artifact)
    rows = [json.loads(line) for line in artifact.read_text().splitlines()]
    symbol = next(row for row in rows if isinstance(row, list) and row[1] == "symbol" and row[2][0] == fixture.__name__)
    symbol[2][2] = "changed-source"
    artifact.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    with pytest.raises(ValueError, match="source changed"):
        load_graph(artifact)


def test_export_and_load_in_independent_processes(tmp_path):
    artifact = tmp_path / "graph.jsonl"
    results = []
    for mode in ("export", "load"):
        command = [
            sys.executable,
            "-m",
            "benchmarks.graph_artifact_evidence",
            mode,
            "--roots",
            "2",
            "--artifact",
            str(artifact),
        ]
        results.append(
            json.loads(subprocess.check_output(command, cwd=Path(__file__).resolve().parents[1], text=True))  # noqa: S603
        )
    exported, loaded = results
    assert exported["pid"] != loaded["pid"]
    assert exported["graph_fingerprint"] == loaded["graph_fingerprint"]
    assert exported["resolved_graph"] == loaded["resolved_graph"]
    assert loaded["compilation_disabled"]
    assert loaded["activations"] == 512


async def test_rich_graph_roundtrip_preserves_facts_sharing_and_provider_lifetimes(tmp_path, monkeypatch):
    from benchmarks import graph_memory_fixture as rich
    from benchmarks.graph_memory_evidence import census
    from clean_ioc.components import Component

    case = rich.build(2)
    artifact = tmp_path / "rich.jsonl"
    dump_graph(case.runtime, artifact)

    def forbidden(*args, **kwargs):
        raise AssertionError("Loading/inspection must not compile or rerun templates")

    monkeypatch.setattr(ContainerBuilder, "build", forbidden)
    monkeypatch.setattr(container._Compiler, "__init__", forbidden)
    monkeypatch.setattr(_legacy, "_set_up_dependencies", forbidden)
    monkeypatch.setattr(_legacy._Registration, "__init__", forbidden)
    for name in ("dependency_for", "worker_for", "worker_decorator_for", "endpoint_decorator_for"):
        monkeypatch.setattr(rich, name, forbidden)
    held = None
    loaded = load_graph(artifact)
    with case.runtime, loaded:
        assert not rich.ACTIVATIONS
        original_counts, loaded_counts = census(case.runtime), census(loaded)
        assert loaded_counts["physical_records"] == original_counts["physical_records"]
        assert loaded_counts["unique_execution_steps"] == original_counts["unique_execution_steps"]
        assert loaded_counts["decorator_objects"] == original_counts["decorator_objects"]
        assert (
            loaded_counts["component_metadata"]["shared_definition_objects"]
            == original_counts["component_metadata"]["shared_definition_objects"]
        )
        assert loaded.graph.manifest(all_roots=True).to_dict() == case.runtime.graph.manifest(all_roots=True).to_dict()
        for occurrence, original in case.runtime._plan.decorator_explanations.items():
            restored = loaded._plan.decorator_explanations[occurrence]
            assert (restored.subject, restored.path, restored.selected, restored.rejected) == (
                original.subject,
                original.path,
                original.selected,
                original.rejected,
            )
        for visit in case.runtime.graph.walk():
            component = visit.component
            if component.kind.value != "registration":
                continue
            expected = case.runtime.graph.explain_decorators(component)
            restored = loaded.graph.explain_decorators(Component(loaded._plan.graph, component.occurrence_id))
            assert restored.selected == expected.selected
            assert restored.rejected == expected.rejected
        restored_case = rich.Fixture(loaded, case.source_ids, case.template_ids, case.callbacks_after_build)
        try:
            held = await rich.resolve_workload(restored_case)
            assert rich.validate(restored_case, held)["workers"] == 22
        finally:
            if held is not None:
                await held.scope.__aexit__(None, None, None)


def test_rich_export_and_load_in_independent_processes(tmp_path):
    results = []
    for mode in ("export", "load"):
        command = [
            sys.executable,
            "-m",
            "benchmarks.graph_memory_artifact_evidence",
            mode,
            "--routes",
            "2",
            "--artifact",
            str(tmp_path / "rich.jsonl"),
        ]
        results.append(
            json.loads(subprocess.check_output(command, cwd=Path(__file__).resolve().parents[1], text=True))  # noqa: S603
        )
    exported, loaded = results
    assert exported["pid"] != loaded["pid"]
    assert exported["artifact_sha256"] == loaded["artifact_sha256"]
    assert exported["graph_fingerprint"] == loaded["graph_fingerprint"]
    assert exported["validated"] == loaded["validated"]
    assert loaded["compilation_disabled"]
    assert loaded["template_calls"] == {}
    assert exported["template_calls"]["source_to_generated_dependency"] == 2
    assert loaded["activations"]["worker"] == 22


def test_codec_rejects_arbitrary_predicate_closures(tmp_path):
    from benchmarks.graph_artifact import _Writer
    from clean_ioc import component_filters as cf

    with (tmp_path / "unsupported.jsonl").open("w") as stream:
        writer = _Writer(stream)
        with pytest.raises(ValueError, match="with_id/with_name"):
            writer.ref(cf.create_filter(lambda component: component.name == "x"))
