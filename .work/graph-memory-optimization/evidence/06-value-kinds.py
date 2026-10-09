"""Opaque-value lifetime regressions for the conservative cache boundary."""

import importlib.util
import json
import sys
import weakref
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

path = Path(__file__).with_name("06-probe.py")
spec = importlib.util.spec_from_file_location("task06_probe", path)
if spec is None or spec.loader is None:
    raise RuntimeError("Cannot load Task 06 probe module")
probe = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)
name = sys.argv[1]
probe.install_probe(name)

from clean_ioc import ContainerBuilder, Provider, derive  # noqa: E402


class Payload:
    pass


class StringPayload(str):
    pass


@dataclass(frozen=True)
class MapKey:
    label: str


class Target:
    pass


class ValueCandidate:
    def __init__(self, value: object):
        self.value = value


class MapCandidate:
    def __init__(self, values: Mapping[MapKey, Provider[Target]]):
        self.values = values


class FirstValues:
    def __init__(self, values: list[ValueCandidate]):
        self.values = values


class FirstMaps:
    def __init__(self, values: list[MapCandidate]):
        self.values = values


class Later:
    def __init__(self, alive: bool):
        self.alive = alive


def run_case(kind, diagnostics, metadata):
    references = []
    calls = []

    def make_value(context):
        calls.append("derive")
        value = StringPayload("opaque string subclass") if kind == "string-subclass" else Payload()
        references.append(weakref.ref(value))
        return [value] if kind == "container" else value

    def make_key(component):
        calls.append("key")
        value = MapKey(component.id)
        references.append(weakref.ref(value))
        return value

    def reject(component):
        calls.append("reject")
        return False

    def observe(context):
        calls.append("observe")
        return bool(references and references[0]() is not None)

    builder = ContainerBuilder()
    if kind == "map-key":
        builder.register(Target, root_policy="dependency_only")
        builder.register_provider_map(Target, key=make_key, key_type=MapKey, root_policy="dependency_only")
        builder.register(MapCandidate, root_policy="dependency_only", when=reject)
        builder.register(FirstMaps)
    else:
        builder.register(
            ValueCandidate, root_policy="dependency_only", arguments={"value": derive(make_value)}, when=reject
        )
        builder.register(FirstValues)
    builder.register(Later, arguments={"alive": derive(observe)})
    with builder.build(explain_metadata=metadata, diagnostics=diagnostics, allow_scope_builders=False) as owner:
        return {
            "kind": kind,
            "diagnostics": diagnostics,
            "explain_metadata": metadata,
            "calls": calls,
            "resolved_argument": owner.resolve(Later).alive,
        }


result = {
    "probe": name,
    "source": probe.evidence.source_provenance(),
    "cases": [
        run_case(kind, diagnostics, metadata)
        for kind in ("object", "string-subclass", "container", "map-key")
        for diagnostics in (False, True)
        for metadata in (False, True)
    ],
}
print(json.dumps(result, indent=2, sort_keys=True))
