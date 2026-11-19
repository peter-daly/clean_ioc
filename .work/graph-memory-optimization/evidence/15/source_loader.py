"""Symmetric current/task14 source loader for additional comparison controls."""

import hashlib
import importlib.abc
import importlib.machinery
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).parent
LOADED = {}


def install(policy):
    class Loader(importlib.machinery.SourceFileLoader):
        def get_code(self, fullname):
            original = Path(self.path)
            path = HERE / (original.name + ".before.txt") if policy == "before" else original
            source = path.read_bytes()
            LOADED[fullname] = hashlib.sha256(source).hexdigest()
            return compile(source, self.path, "exec")

    class Finder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname not in ("clean_ioc.container", "benchmarks.graph_artifact"):
                return None
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec is None or spec.origin is None:
                raise RuntimeError("Missing task15 comparison source")
            spec.loader = Loader(fullname, spec.origin)
            return spec

    sys.path.insert(0, str(ROOT))
    sys.meta_path.insert(0, Finder())
