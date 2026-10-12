"""Symmetric captured/current loader; proof variants never edit production files."""

import hashlib
import importlib.abc
import importlib.machinery
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).parent
LOADED = {}
ORIGINAL = "plan.graph._drafts = {occurrence: drafts[occurrence] for occurrence in live}"
TRANSFER = "plan.graph._drafts = {occurrence: drafts.pop(occurrence) for occurrence in live}"


def install(policy):
    class Loader(importlib.machinery.SourceFileLoader):
        def get_code(self, fullname):
            path = Path(self.path) if policy == "after" else HERE / "clean_ioc__container.py.before.txt"
            source = path.read_text()
            if policy in ("transfer", "release-all"):
                assert source.count(ORIGINAL) == 1  # noqa: S101
                replacement = TRANSFER if policy == "transfer" else ORIGINAL + "\n        del drafts"
                source = source.replace(ORIGINAL, replacement)
            LOADED[fullname] = hashlib.sha256(source.encode()).hexdigest()
            return compile(source, self.path, "exec")

    class Finder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname != "clean_ioc.container":
                return None
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec is None or spec.origin is None:
                raise RuntimeError("Missing container source")
            spec.loader = Loader(fullname, spec.origin)
            return spec

    sys.path.insert(0, str(ROOT))
    sys.meta_path.insert(0, Finder())
