"""Experimental, source-coupled persistence of a constructor-only compiled plan.

This is deliberately outside the public library. Artifacts are trusted local build
outputs: loading imports their referenced Python modules. No live container,
service instance, Python bytecode, or executable pickle is persisted.
"""

import dataclasses
import gc
import hashlib
import importlib
import json
import sys
from enum import Enum
from pathlib import Path
from types import FunctionType, MappingProxyType
from typing import Any, TextIO

from clean_ioc import Container, components, container, metadata, tooling
from clean_ioc import _decorator_templates as templates
from clean_ioc import _legacy as legacy
from clean_ioc import _legacy_configuration as configuration

SCHEMA = 3
_REPO = Path(__file__).resolve().parents[1]
_DATACLASSES = (
    container._PlanSet,
    container._RootPlan,
    container._CompiledDependency,
    container._CleanupOwnerDescriptor,
    container._TransientRegistrationStep,
    container._PerResolutionRegistrationStep,
    container._ScopedRegistrationStep,
    container._SingletonRegistrationStep,
    container._OccurrenceLayers,
    components._ComponentRecord,
    tooling.CompiledGraph,
    tooling.GraphRoot,
    tooling.DefinitionOrigin,
    tooling.SourceLocation,
    tooling._CandidateRecord,
    tooling.CandidateDecision,
    tooling.BuildReport,
    templates.RegistrationInfo,
    configuration.DependencySettings,
    metadata.Tag,
)
_SLOTTED = (components._ComponentGraph, components.Component, legacy._Registration, legacy.Dependency)
_CLASSES = {f"{cls.__module__}:{cls.__qualname__}": cls for cls in (*_DATACLASSES, *_SLOTTED)}
_FIELDS = {
    cls: tuple(field.name for field in dataclasses.fields(cls)) if cls in _DATACLASSES else tuple(cls.__slots__)
    for cls in _CLASSES.values()
}
_SPECIAL_SYMBOLS = {
    id(legacy.default_parent_node_filter): ("clean_ioc._legacy", "default_parent_node_filter"),
    id(configuration.EMPTY): ("clean_ioc._legacy_configuration", "EMPTY"),
    id(configuration.UNKNOWN): ("clean_ioc._legacy_configuration", "UNKNOWN"),
}


def _source_hash(module) -> str | None:
    path = getattr(module, "__file__", None)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if path else None


def _compatibility() -> dict[str, Any]:
    digest = hashlib.sha256()
    paths = sorted((_REPO / "clean_ioc").rglob("*.py"))
    paths += [Path(__file__), _REPO / "uv.lock"]
    for path in paths:
        digest.update(str(path.relative_to(_REPO)).encode())
        digest.update(path.read_bytes())
    return {
        "schema": SCHEMA,
        "python": list(sys.version_info[:3]),
        "implementation": sys.implementation.name,
        "source_sha256": digest.hexdigest(),
    }


def _symbol(module_name: str, qualname: str):
    if module_name == "__main__" or "<" in qualname:
        raise ValueError("Artifact symbols must be importable module-level objects")
    module = importlib.import_module(module_name)
    value = module
    for part in qualname.split("."):
        value = getattr(value, part)
    return value, module


class _Writer:
    """Postorder object records preserve sharing, without a second full JSON tree."""

    def __init__(self, stream: TextIO):
        self.stream = stream
        self.memo: dict[int, int] = {}
        self.active: set[int] = set()
        self.module_hashes: dict[str, str | None] = {}

    def symbol(self, value, module_name: str, qualname: str):
        imported, module = _symbol(module_name, qualname)
        if imported is not value:
            raise ValueError(f"Symbol does not round-trip: {module_name}:{qualname}")
        if module_name not in self.module_hashes:
            self.module_hashes[module_name] = _source_hash(module)
        return [module_name, qualname, self.module_hashes[module_name]]

    def ref(self, value):
        if value is None or type(value) in (bool, float):
            return value
        identity = id(value)
        if identity in self.active:
            raise ValueError("Cyclic metadata is outside this experiment")
        if identity in self.memo:
            return [self.memo[identity]]
        self.active.add(identity)
        kind, payload = self.encode(value)
        index = len(self.memo)
        self.memo[identity] = index
        self.active.remove(identity)
        self.stream.write(json.dumps([index, kind, payload], separators=(",", ":"), allow_nan=False) + "\n")
        return [index]

    def encode(self, value):
        cls = type(value)
        if cls is str:
            return "str", value
        if cls is int:
            return "int", value
        if id(value) in _SPECIAL_SYMBOLS:
            return "symbol", self.symbol(value, *_SPECIAL_SYMBOLS[id(value)])
        if isinstance(value, Enum):
            return "enum", [self.symbol(cls, cls.__module__, cls.__qualname__), value.name]
        if isinstance(value, (type, FunctionType)):
            return "symbol", self.symbol(value, value.__module__, value.__qualname__)
        if cls in _FIELDS:
            if isinstance(value, legacy._Registration) and value.is_instance:
                raise ValueError("Instance registrations are outside this experiment")
            fields = [self.ref(getattr(value, name)) for name in _FIELDS[cls]]
            return "record", [f"{cls.__module__}:{cls.__qualname__}", fields]
        if cls is MappingProxyType:
            # Separate read-only views can share one backing dictionary. Saving
            # their items independently duplicates large metadata maps on load.
            referents = gc.get_referents(value)
            if len(referents) != 1 or not isinstance(referents[0], dict):
                raise ValueError("Expected a mapping proxy backed by a dictionary")
            return "mapping", self.ref(referents[0])
        if cls is dict:
            return "dict", [[self.ref(key), self.ref(item)] for key, item in value.items()]
        if cls in (tuple, list, frozenset):
            return cls.__name__, [self.ref(item) for item in value]
        raise ValueError(f"Unsupported artifact value: {cls.__module__}.{cls.__qualname__}")


class _Reader:
    def __init__(self):
        self.objects: list[Any] = []
        self.module_hashes: dict[str, str | None] = {}

    def deref(self, value):
        if not isinstance(value, list):
            if value is not None and type(value) not in (bool, int, float):
                raise ValueError("Invalid artifact scalar")
            return value
        if (
            len(value) != 1
            or not isinstance(value[0], int)
            or isinstance(value[0], bool)
            or not 0 <= value[0] < len(self.objects)
        ):
            raise ValueError("Invalid artifact reference")
        return self.objects[value[0]]

    def symbol(self, specification):
        module_name, qualname, expected_hash = specification
        value, module = _symbol(module_name, qualname)
        if module_name not in self.module_hashes:
            self.module_hashes[module_name] = _source_hash(module)
        if self.module_hashes[module_name] != expected_hash:
            raise ValueError(f"Artifact source changed: {module_name}")
        return value

    def decode(self, kind, payload):
        if kind in ("str", "int"):
            return payload
        if kind == "symbol":
            return self.symbol(payload)
        if kind == "enum":
            return self.symbol(payload[0])[payload[1]]
        if kind == "record":
            name, values = payload
            cls = _CLASSES.get(name)
            if cls is None or len(values) != len(_FIELDS[cls]):
                raise ValueError(f"Unsupported artifact record: {name}")
            # Do not invoke compiler constructors or signature inspection.
            obj = object.__new__(cls)
            for field, value in zip(_FIELDS[cls], values):
                object.__setattr__(obj, field, self.deref(value))
            return obj
        if kind == "mapping":
            return MappingProxyType(self.deref(payload))
        if kind == "dict":
            return {self.deref(key): self.deref(value) for key, value in payload}
        factories = {"tuple": tuple, "list": list, "frozenset": frozenset}
        if kind in factories:
            return factories[kind](self.deref(value) for value in payload)
        raise ValueError(f"Unsupported artifact record kind: {kind}")


def _check_plan(plan):
    if not isinstance(plan, container._PlanSet):
        raise ValueError("Artifact did not contain a compiled plan")
    if plan._blueprint is not None or plan.diagnostics or plan.slots or plan.validation_rules:
        raise ValueError("Use diagnostics=False, allow_scope_builders=False, with no slots or validation callbacks")
    if plan.provider_roots or plan.managed_provider_roots or plan.warmup_infos or plan.graph._views:
        raise ValueError("Providers and warmups are outside this experiment; build with provider_roots=()")
    if plan.graph._records is None or plan.graph._drafts:
        raise ValueError("The component graph must be frozen")
    for record in plan.graph._records.values():
        if record.boundary is not None:
            raise ValueError("Boundaries are outside this experiment")
        if record.activation != components.ComponentActivation.constructor:
            raise ValueError("Only constructor registrations are supported; instances and factories are excluded")


def dump_graph(runtime: Container, path: Path) -> dict[str, int]:
    """Export an unresolved compiled plan, keeping its records and shared steps."""
    _check_plan(runtime._plan)
    if runtime._resolution_started or runtime._singletons or runtime._scoped:
        raise ValueError("Export before resolving any services")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("w") as stream:
            stream.write(json.dumps({"compatibility": _compatibility()}) + "\n")
            writer = _Writer(stream)
            plan = writer.ref(runtime._plan)
            owner = writer.ref(runtime._owned_token)
            stream.write(json.dumps({"plan": plan, "owner": owner}) + "\n")
        temporary.replace(path)
        return {"artifact_bytes": path.stat().st_size, "serialized_objects": len(writer.memo)}
    finally:
        temporary.unlink(missing_ok=True)


def load_graph(path: Path) -> Container:
    """Import runtime symbols and rehydrate a plan; never build a registry."""
    reader = _Reader()
    with path.open() as stream:
        if json.loads(next(stream))["compatibility"] != _compatibility():
            raise ValueError("Artifact schema, Python version, or Clean IoC source does not match")
        for line in stream:
            record = json.loads(line)
            if isinstance(record, dict):
                plan, owner = reader.deref(record["plan"]), reader.deref(record["owner"])
                if stream.read(1):
                    raise ValueError("Unexpected content after artifact footer")
                _check_plan(plan)
                return Container(plan, owner)
            index, kind, payload = record
            if index != len(reader.objects):
                raise ValueError("Invalid artifact record order")
            reader.objects.append(reader.decode(kind, payload))
    raise ValueError("Incomplete artifact: missing footer")
