"""Reuse Task06 exact-attribution/failure probe with Task07 import transforms."""

import importlib.util
import runpy
import sys
from pathlib import Path

path = Path(__file__).with_name("07-probe.py")
spec = importlib.util.spec_from_file_location("task07_probe", path)
if spec is None or spec.loader is None:
    raise RuntimeError("Cannot load Task07 probe")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
probe.install(sys.argv.pop(1))
sys.argv[0] = str(path.with_name("06-semantics.py"))
runpy.run_path(sys.argv[0], run_name="__main__")
