"""Bounded Task08 experiment: prepared bytecode, adaptive indexes and codec."""

# ruff: noqa: E721
import argparse
import asyncio
import hashlib
import importlib.abc
import importlib.machinery
import json
import marshal
import runpy
import sys
import time
import tracemalloc
from collections.abc import MutableMapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent
sys.path.insert(0, str(ROOT))
MISSING = object()
PROBE = "baseline"
HASHES = {}


class CompactIndex(MutableMapping):
    """Append/update exact ints compactly; delegate general semantics to dict."""

    __slots__ = ("_values", "_keys", "_sparse", "_dict")
    LIMIT = 1 << 20

    def __init__(self):
        self._values = []
        self._keys = []
        self._sparse = {}
        self._dict = None

    def raw_items(self):
        if self._dict is not None:
            yield from self._dict.items()
        else:
            for key in self._keys:
                yield key, self[key]

    def promote(self):
        if self._dict is None:
            self._dict = dict(self.raw_items())
            self._values = []
            self._keys = []
            self._sparse = {}
        return self._dict

    def __getitem__(self, key):
        if self._dict is not None:
            return self._dict[key]
        if type(key) is not int:
            return self.promote()[key]
        if 0 <= key < len(self._values):
            value = self._values[key]
            if value is not MISSING:
                return value
        return self._sparse[key]

    def get(self, key, default=None):
        if self._dict is not None:
            return self._dict.get(key, default)
        if type(key) is not int:
            return self.promote().get(key, default)
        if 0 <= key < len(self._values):
            value = self._values[key]
            if value is not MISSING:
                return value
        return self._sparse.get(key, default)

    def __contains__(self, key):
        if self._dict is not None:
            return key in self._dict
        if type(key) is not int:
            return key in self.promote()
        return self.get(key, MISSING) is not MISSING

    def __setitem__(self, key, value):
        if self._dict is not None:
            self._dict[key] = value
            return
        if type(key) is not int:
            self.promote()[key] = value
            return
        previous = self.get(key, MISSING)
        if previous is not MISSING:
            if 0 <= key < len(self._values) and self._values[key] is not MISSING:
                self._values[key] = value
            else:
                self._sparse[key] = value
            return
        self._keys.append(key)
        if 0 <= key < min(self.LIMIT, max(64, len(self._keys) * 4)):
            if key >= len(self._values):
                self._values.extend([MISSING] * (key + 1 - len(self._values)))
            self._values[key] = value
        else:
            self._sparse[key] = value

    def __delitem__(self, key):
        del self.promote()[key]

    def __iter__(self):
        # A live mutable iterator must inherit dict's size/key-change behavior.
        return iter(self.promote())

    def keys(self):
        return self.promote().keys()

    def values(self):
        return self.promote().values()

    def items(self):
        return self.promote().items()

    def __reversed__(self):
        return reversed(self.promote())

    def __len__(self):
        return len(self._dict) if self._dict is not None else len(self._keys)

    def popitem(self):
        return self.promote().popitem()

    def clear(self):
        self._values = []
        self._keys = []
        self._sparse = {}
        if self._dict is not None:
            self._dict.clear()

    def copy(self):
        return dict(self.raw_items())

    def __or__(self, other):
        return self.promote() | other

    def __ror__(self, other):
        return other | self.promote()

    def __ior__(self, other):
        self.promote().__ior__(other)
        return self

    def capacity(self):
        return {
            "entries": len(self),
            "dense_length": len(self._values),
            "sparse_entries": len(self._sparse),
            "promoted": self._dict is not None,
            "shallow_bytes": sum(map(sys.getsizeof, (self, self._values, self._keys, self._sparse)))
            + (sys.getsizeof(self._dict) if self._dict is not None else 0),
        }


def transform(source, module, probe):
    if module == "clean_ioc.container":
        if probe in ("origins", "both"):
            source = source.replace(
                "self.origins: dict[int, DefinitionOrigin] = {}", "self.origins = _08CompactIndex()"
            )
        if probe in ("decorators", "both"):
            source = source.replace(
                "self.decorator_explanations: dict[int, _DecoratorExplanation] = {}",
                "self.decorator_explanations = _08CompactIndex()",
            )
        return source
    if probe == "baseline":
        return source
    source = source.replace("SCHEMA = 7", "SCHEMA = 8008")
    source = source.replace('"schema": SCHEMA,', '"schema": SCHEMA, "task08": _08Compatibility(),')
    source = source.replace(
        "if len(referents) != 1 or not isinstance(referents[0], dict):",
        "if len(referents) != 1 or type(referents[0]) not in (dict, _08CompactIndex):",
    )
    source = source.replace(
        '        if cls is dict:\n            return "dict",',
        "        if cls is _08CompactIndex:\n"
        "            if value._dict is not None:\n"
        '                return "dict", [[self.ref(key), self.ref(item)] for key, item in value.raw_items()]\n'
        '            return "compact08", [[self.ref(key), self.ref(item)] for key, item in value.raw_items()]\n'
        '        if cls is dict:\n            return "dict",',
    )
    source = source.replace(
        '        if kind == "mapping":',
        '        if kind == "compact08":\n'
        "            result = _08CompactIndex()\n"
        "            if not isinstance(payload, list):\n"
        '                raise ValueError("Invalid compact index payload")\n'
        "            for pair in payload:\n"
        "                if not isinstance(pair, list) or len(pair) != 2:\n"
        '                    raise ValueError("Invalid compact index pair")\n'
        "                key, value = self.deref(pair[0]), self.deref(pair[1])\n"
        "                if type(key) is not int or key in result:\n"
        '                    raise ValueError("Invalid compact index key")\n'
        "                result[key] = value\n"
        "            return result\n"
        '        if kind == "mapping":',
    )
    return source


def compatibility():
    return {"probe": PROBE, "hashes": HASHES, "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


class Loader(importlib.machinery.SourceFileLoader):
    def get_code(self, fullname):
        manifest = json.loads((HERE / "08-prepared.json").read_text())
        module_name = fullname.replace(".", "-")
        original = Path(self.path).read_bytes()
        if hashlib.sha256(original).hexdigest() != manifest["original"][fullname]:
            raise RuntimeError("Task08 source baseline changed")
        source = HERE / f"08-{PROBE}-{module_name}.py.txt"
        payload = HERE / f"08-{PROBE}-{module_name}-{sys.implementation.cache_tag}.bin"
        changed = source.read_bytes()
        expected = manifest["changed"][PROBE][fullname]
        if hashlib.sha256(changed).hexdigest() != expected:
            raise RuntimeError("Task08 prepared source changed")
        HASHES[fullname] = expected
        if payload.exists():
            data = payload.read_bytes()
            if hashlib.sha256(data).hexdigest() != manifest["bytecode"][PROBE][fullname]:
                raise RuntimeError("Task08 bytecode changed")
            return marshal.loads(data)  # noqa: S302
        return compile(changed, self.path, "exec")

    def exec_module(self, module):
        module._08CompactIndex = CompactIndex
        module._08Compatibility = compatibility
        super().exec_module(module)


class Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname not in ("clean_ioc.container", "benchmarks.graph_artifact"):
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.origin is None:
            raise RuntimeError("Missing probe source")
        spec.loader = Loader(fullname, spec.origin)
        return spec


def install(probe):
    global PROBE
    PROBE = probe
    sys.meta_path.insert(0, Finder())


def prepare():
    result = {"original": {}, "changed": {}, "bytecode": {}}
    for probe in ("baseline", "origins", "decorators", "both"):
        result["changed"][probe] = {}
        result["bytecode"][probe] = {}
        for module in ("clean_ioc.container", "benchmarks.graph_artifact"):
            path = ROOT / (module.replace(".", "/") + ".py")
            source = path.read_text()
            result["original"][module] = hashlib.sha256(source.encode()).hexdigest()
            changed = transform(source, module, probe)
            name = module.replace(".", "-")
            (HERE / f"08-{probe}-{name}.py.txt").write_text(changed)
            result["changed"][probe][module] = hashlib.sha256(changed.encode()).hexdigest()
            data = marshal.dumps(compile(changed, str(path), "exec"))
            (HERE / f"08-{probe}-{name}-{sys.implementation.cache_tag}.bin").write_bytes(data)
            result["bytecode"][probe][module] = hashlib.sha256(data).hexdigest()
    (HERE / "08-prepared.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "measure", "pytest", "lifetimes", "semantics", "export", "load"))
    parser.add_argument("--probe", choices=("baseline", "origins", "decorators", "both"), default="baseline")
    parser.add_argument("--routes", type=int, default=8)
    parser.add_argument("--heap", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--inspection", action="store_true")
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--output", type=Path)
    args, rest = parser.parse_known_args()
    if args.mode == "prepare":
        result = prepare()
    else:
        install(args.probe)
        from benchmarks import graph_memory_evidence as evidence

        if args.mode == "pytest":
            import pytest

            raise SystemExit(pytest.main(rest))
        if args.mode in ("lifetimes", "semantics"):
            source = HERE / ("06-value-kinds.py" if args.mode == "lifetimes" else "06-semantics.py")
            sys.argv = [str(source), *(["baseline"] if args.mode == "lifetimes" else rest)]
            runpy.run_path(str(source), run_name="__main__")
            return
        if args.mode == "measure":
            result = asyncio.run(
                evidence.measure(
                    args.routes,
                    args.heap,
                    args.diagnostics,
                    inspection=args.inspection,
                    explain_metadata=args.full,
                    allow_scope_builders=False,
                )
            )
        else:
            from benchmarks.graph_artifact import SCHEMA, dump_graph, load_graph
            from clean_ioc import container

            result = {
                "before": evidence._memory(False),
                "instrumentation": "tracemalloc" if args.heap else "none",
                "schema": SCHEMA,
                "routes": args.routes,
                "full": args.full,
            }
            if args.heap:
                tracemalloc.start()
            started = time.perf_counter()
            if args.mode == "export":
                from benchmarks.graph_memory_fixture import build

                fixture = build(args.routes, explain_metadata=args.full, allow_scope_builders=False)
                runtime = fixture.runtime
            else:

                def forbidden(*arguments, **keywords):
                    raise AssertionError("Load attempted compilation")

                container._Compiler.__init__ = forbidden
                container.ContainerBuilder.build = forbidden
                runtime = load_graph(args.artifact)
            result["prepare_seconds"] = time.perf_counter() - started
            result["prepared"] = evidence._memory(args.heap)
            if args.mode == "export":
                if args.heap:
                    tracemalloc.reset_peak()
                started = time.perf_counter()
                result.update(dump_graph(runtime, args.artifact))
                result["export_seconds"] = time.perf_counter() - started
                result["exported"] = evidence._memory(args.heap)
            else:
                result["artifact_bytes"] = args.artifact.stat().st_size
            if args.heap:
                tracemalloc.stop()
            result["graph"] = evidence.census(runtime)
            if args.full:
                started = time.perf_counter()
                result["manifest"] = runtime.graph.manifest(all_roots=True).fingerprint
                result["inspection_seconds"] = time.perf_counter() - started
            from benchmarks.graph_memory_fixture import Fixture, resolve_workload, validate

            if args.mode == "load":
                from benchmarks.graph_memory_fixture import TEMPLATE_CALLS, RouteSource

                sources = {root.component.name: root.component.id for root in runtime._plan.roots[RouteSource]}
                fixture = Fixture(runtime, sources, {}, dict(TEMPLATE_CALLS))  # ty: ignore[invalid-argument-type]

            async def resolve():
                started = time.perf_counter()
                held = await resolve_workload(fixture)
                result["resolve_seconds"] = time.perf_counter() - started
                result["validated"] = validate(fixture, held)
                await held.scope.__aexit__(None, None, None)
                await runtime.__aexit__(None, None, None)

            asyncio.run(resolve())
        result["probe"] = args.probe
        result["mode"] = args.mode
        result["compatibility"] = compatibility()
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded)


if __name__ == "__main__":
    main()
