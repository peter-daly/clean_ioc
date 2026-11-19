"""Isolated import-time Task 07 probes. Production files remain unchanged."""

import argparse
import ast
import asyncio
import collections
import gc
import hashlib
import importlib.abc
import importlib.machinery
import json
import marshal
import statistics
import subprocess
import sys
import time
import weakref
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


class IndexedMapping(MutableMapping):
    """Bounded dense positive IDs, explicit insertion order, sparse fallback."""

    __slots__ = ("_values", "_keys", "_sparse")
    missing = object()

    def __init__(self):
        self._values = []
        self._keys = []
        self._sparse = {}

    def __getitem__(self, key):
        if isinstance(key, int) and 0 <= key < len(self._values):
            value = self._values[key]
            if value is not self.missing:
                return value
        return self._sparse[key]

    def __setitem__(self, key, value):
        if key not in self:
            self._keys.append(key)
        if isinstance(key, int) and 0 <= key <= max(1024, len(self._values) * 2):
            if key >= len(self._values):
                self._values.extend([self.missing] * (key + 1 - len(self._values)))
            self._values[key] = value
            self._sparse.pop(key, None)
        else:
            self._sparse[key] = value

    def __delitem__(self, key):
        self[key]
        self._keys.remove(key)
        if key in self._sparse:
            del self._sparse[key]
        else:
            self._values[key] = self.missing

    def __iter__(self):
        return iter(self._keys)

    def __len__(self):
        return len(self._keys)


def transform(source, probe):
    tree = ast.parse(source)
    if probe == "slots":
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name in (
                "_Step",
                "_ObservedRegistrationMixin",
                "_ObservedScopedCacheMixin",
            ):
                fields = ("__weakref__",) if node.name == "_Step" else ()
                node.body.insert(1, ast.parse(f"__slots__ = {fields!r}").body[0])
        return ast.unparse(ast.fix_missing_locations(tree))
    if probe == "prelookup":
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name != "_compile_registration":
                continue
            block = next(item for item in node.body if isinstance(item, ast.Try)).body
            index = next(
                i
                for i, item in enumerate(block)
                if isinstance(item, ast.Assign)
                and isinstance(item.value, ast.Call)
                and isinstance(item.value.func, ast.Name)
                and item.value.func.id == "step_type"
            )
            construction = block[index]
            cache = block[index + 1]
            if (
                not isinstance(cache, ast.If)
                or not isinstance(construction, ast.Assign)
                or not isinstance(construction.value, ast.Call)
            ):
                raise RuntimeError("Unexpected cache construction shape")
            expressions = {}
            for keyword in construction.value.keywords:
                if keyword.arg in ("cleanup_owner", "sync_supported"):
                    expressions[keyword.arg] = keyword.value
                    keyword.value = ast.Name(id=f"candidate_{keyword.arg}", ctx=ast.Load())
            assignments = [
                ast.Assign(targets=[ast.Name(id=f"candidate_{key}", ctx=ast.Store())], value=value)
                for key, value in expressions.items()
            ]

            class Rewrite(ast.NodeTransformer):
                def visit_Attribute(self, node):  # noqa: N802
                    if isinstance(node.value, ast.Name) and node.value.id == "step" and node.attr in expressions:
                        return ast.Name(id=f"candidate_{node.attr}", ctx=ast.Load())
                    return self.generic_visit(node)

            cache = Rewrite().visit(cache)
            miss = next(item for item in cache.body if isinstance(item, ast.If))
            miss.body.insert(0, construction)
            cache.orelse = [construction, *cache.orelse]
            block[index : index + 2] = [*assignments, cache]
        return ast.unparse(ast.fix_missing_locations(tree))
    if probe == "indexes":
        source = source.replace(
            "self.decorator_explanations: dict[int, _DecoratorExplanation] = {}",
            "self.decorator_explanations: dict[int, _DecoratorExplanation] = _07IndexedMapping()",
        )
        return source.replace(
            "self.origins: dict[int, DefinitionOrigin] = {}",
            "self.origins: dict[int, DefinitionOrigin] = _07IndexedMapping()",
        )
    return source


class Loader(importlib.machinery.SourceFileLoader):
    def get_code(self, fullname):
        source = self.get_data(self.path).decode()
        prepared = Path(__file__).with_name(f"07-{PROBE}-container.py.txt")
        manifest = Path(__file__).with_name("07-prepared-sources.json")
        if prepared.exists():
            facts = json.loads(manifest.read_text())
            if hashlib.sha256(source.encode()).hexdigest() != facts["original_sha256"]:
                raise RuntimeError("Prepared source baseline changed")
            changed = prepared.read_text()
            if hashlib.sha256(changed.encode()).hexdigest() != facts["transformed_sha256"][PROBE]:
                raise RuntimeError("Prepared probe source changed")
        else:
            changed = transform(source, PROBE)
        TRANSFORM_HASHES[fullname] = hashlib.sha256(changed.encode()).hexdigest()
        bytecode = Path(__file__).with_name(f"07-{PROBE}-{sys.implementation.cache_tag}-container.code.bin")
        if bytecode.exists():
            if not prepared.exists():
                raise RuntimeError("Prepared bytecode has no source manifest")
            payload = bytecode.read_bytes()
            if hashlib.sha256(payload).hexdigest() != facts["bytecode_sha256"][PROBE]:
                raise RuntimeError("Prepared bytecode changed")
            return marshal.loads(payload)  # noqa: S302
        return compile(changed, self.path, "exec")

    def exec_module(self, module):
        module._07IndexedMapping = IndexedMapping
        super().exec_module(module)


class Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != "clean_ioc.container":
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.origin is None:
            raise RuntimeError("Missing container import spec")
        spec.loader = Loader(fullname, spec.origin)
        return spec


PROBE = "baseline"
TRANSFORM_HASHES = {}


def install(probe):
    global PROBE
    PROBE = probe
    sys.meta_path.insert(0, Finder())


def inventory(runtime, components):
    result: dict[str, Any] = {"classes": [], "primary": []}
    for module in (runtime, components):
        for name, cls in vars(module).items():
            if not isinstance(cls, type) or cls.__module__ != module.__name__:
                continue
            if name.startswith("_") and ("Step" in name or "Component" in name or "Mixin" in name):
                result["classes"].append(
                    {
                        "name": name,
                        "mro": [base.__name__ for base in cls.__mro__],
                        "dict_offset": cls.__dictoffset__,
                        "weakref_offset": cls.__weakrefoffset__,
                        "basicsize": cls.__basicsize__,
                        "slots": {base.__name__: base.__dict__.get("__slots__") for base in cls.__mro__},
                    }
                )
    counts = collections.Counter()
    for name, cls in vars(runtime).items():
        if (
            isinstance(cls, type)
            and cls.__module__ == runtime.__name__
            and issubclass(cls, runtime._Step)
            and "__init__" in cls.__dict__
        ):
            original = cls.__init__

            def init(self, *args, _init=original, _name=name, **kwargs):
                counts[_name] += 1
                _init(self, *args, **kwargs)

            cls.__init__ = init
    original = runtime._Compiler.compile

    def compile_primary(self, *args, **kwargs):
        value = original(self, *args, **kwargs)
        objects = gc.get_objects()
        live = collections.Counter(type(obj).__name__ for obj in objects if isinstance(obj, runtime._Step))
        shallow = collections.Counter()
        for obj in objects:
            if isinstance(obj, runtime._Step):
                shallow[type(obj).__name__] += sys.getsizeof(obj)
        drafts = list(self.graph._drafts.values())
        fields = (
            "service_type",
            "implementation",
            "implementation_type",
            "lifespan",
            "name",
            "tags",
            "build_args",
            "kind",
            "activation",
            "boundary",
            "declared_service_type",
        )
        started = time.perf_counter()
        pool = {}
        for draft in drafts:
            key = tuple(id(getattr(draft, name)) for name in fields)
            pool.setdefault(key, tuple(getattr(draft, name) for name in fields))
        packing_time = time.perf_counter() - started
        indexes = {}
        for name in ("origins", "decorator_explanations"):
            mapping = getattr(self, name)
            keys = list(mapping)
            indexes[name] = {
                "entries": len(mapping),
                "min": min(keys, default=0),
                "max": max(keys, default=0),
                "shallow_bytes": sys.getsizeof(mapping),
                "unique_values": len({id(item) for item in mapping.values()}),
                "sequence_capacity_bytes": (max(keys, default=-1) + 1) * 8,
                "insertion_order_sorted": keys == sorted(keys),
            }
        result["primary"].append(
            {
                "drafts": len(drafts),
                "live_steps": live,
                "step_shallow_bytes": shallow,
                "draft_tuple_identity_definitions": len(pool),
                "draft_pool_shallow_bytes": sys.getsizeof(pool)
                + sum(sys.getsizeof(key) + sys.getsizeof(value) for key, value in pool.items()),
                "draft_packing_seconds": packing_time,
                "indexes": indexes,
            }
        )
        return value

    runtime._Compiler.compile = compile_primary
    result["created_steps"] = counts
    value = runtime._ValueStep(1)
    result["weakref_value_step"] = weakref.ref(value)() is value
    result["value_step_shallow_bytes"] = sys.getsizeof(value)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("measure", "repeat", "inventory", "pytest", "lifetimes"))
    parser.add_argument("--probe", choices=("baseline", "slots", "prelookup", "indexes"), default="baseline")
    parser.add_argument("--routes", type=int, default=8)
    parser.add_argument("--heap", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--overlays", action="store_true")
    parser.add_argument("--output", type=Path)
    args, rest = parser.parse_known_args()
    result: dict[str, Any]
    if args.mode == "repeat":
        runs = []
        for repeat in range(3):
            for heap in (False, True):
                command = [sys.executable, __file__, "measure", "--probe", args.probe, "--routes", str(args.routes)]
                command += [
                    flag
                    for enabled, flag in (
                        (heap, "--heap"),
                        (args.full, "--full"),
                        (args.diagnostics, "--diagnostics"),
                        (args.overlays, "--overlays"),
                    )
                    if enabled
                ]
                run = json.loads(subprocess.check_output(command, text=True))  # noqa: S603
                run["repeat"] = repeat + 1
                runs.append(run)
                print(f"{args.probe}: {repeat+1}, traced={heap}", file=sys.stderr)
        normal = [run for run in runs if run["instrumentation"] == "none"]
        traced = [run for run in runs if run["instrumentation"] == "tracemalloc"]
        result = {
            "runs": runs,
            "medians": {
                key: statistics.median(run[key] for run in normal) for key in ("build_seconds", "resolve_seconds")
            },
        }
        result["medians"]["prepared"] = {
            key: statistics.median(run["prepared"][key] for run in group)
            for group, keys in (
                (normal, ("rss_bytes", "peak_rss_bytes")),
                (traced, ("traced_retained_bytes", "traced_peak_bytes")),
            )
            for key in keys
        }
    else:
        install(args.probe)
        from benchmarks import graph_memory_evidence as evidence
        from clean_ioc import components, container

        if args.mode == "pytest":
            import pytest

            raise SystemExit(pytest.main(rest))
        if args.mode == "lifetimes":
            import runpy

            sys.argv = [str(ROOT / ".work/graph-memory-optimization/evidence/06-value-kinds.py"), "baseline"]
            runpy.run_path(sys.argv[0], run_name="__main__")
            return
        capture = inventory(container, components) if args.mode == "inventory" else None
        result = asyncio.run(
            evidence.measure(
                args.routes, args.heap, args.diagnostics, explain_metadata=args.full, allow_scope_builders=args.overlays
            )
        )
        if capture is not None:
            result["layout_inventory"] = capture
        result["transformed_source_sha256"] = TRANSFORM_HASHES
    result["probe"] = args.probe
    result["probe_source_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded)


if __name__ == "__main__":
    main()
