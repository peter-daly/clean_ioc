"""Symmetric task15/current components source loader, installed before imports."""

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
            path = HERE / "clean_ioc__components.py.before.txt" if policy == "before" else Path(self.path)
            source = path.read_bytes()
            LOADED[fullname] = hashlib.sha256(source).hexdigest()
            return compile(source, self.path, "exec")

    class Finder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname != "clean_ioc.components":
                return None
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec is None or spec.origin is None:
                raise RuntimeError("Missing components source")
            spec.loader = Loader(fullname, spec.origin)
            return spec

    sys.path.insert(0, str(ROOT))
    sys.meta_path.insert(0, Finder())
