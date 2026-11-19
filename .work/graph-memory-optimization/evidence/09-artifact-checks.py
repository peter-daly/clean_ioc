"""Unsupported backing/value rejection preserves existing published artifacts."""

# ruff: noqa: S101
import importlib.util
import json
import tempfile
from collections import UserDict
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

path = Path(__file__).with_name("09-probe.py")
spec = importlib.util.spec_from_file_location("task09_probe", path)
if spec is None or spec.loader is None:
    raise RuntimeError("Missing Task09 probe")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
probe.install("both")
from benchmarks.graph_artifact import dump_graph, load_graph  # noqa: E402
from benchmarks.graph_artifact_fixture import build  # noqa: E402
from clean_ioc import Container  # noqa: E402

runtime = build(1)
bad_value = probe.CompactIndex()
bad_value[1] = object()
failures = []
with tempfile.TemporaryDirectory() as directory:
    artifact = Path(directory) / "graph.jsonl"
    for backing in (UserDict(), bad_value):
        artifact.write_text("previously-published")
        bad = Container(replace(runtime._plan, occurrence_origins=MappingProxyType(backing)), runtime._owned_token)
        try:
            dump_graph(bad, artifact)
        except ValueError as error:
            failures.append(str(error))
        else:
            raise AssertionError("Unsupported encoding was published")
        assert artifact.read_text() == "previously-published"
        assert not artifact.with_suffix(".jsonl.tmp").exists()
    dump_graph(runtime, artifact)
    rows = artifact.read_text().splitlines()
    header = json.loads(rows[0])
    for invalid in (None, [[True, None]], [[1, None], [1, None]]):
        artifact.write_text(json.dumps(header) + "\n" + json.dumps([0, "compact09", invalid]) + "\n")
        try:
            load_graph(artifact)
        except ValueError as error:
            failures.append(str(error))
        else:
            raise AssertionError("Malformed compact row was loaded")
print(
    json.dumps(
        {
            "failed_before_publication": True,
            "prior_output_preserved": True,
            "malformed_loads_rejected": True,
            "errors": failures,
        },
        indent=2,
    )
)
