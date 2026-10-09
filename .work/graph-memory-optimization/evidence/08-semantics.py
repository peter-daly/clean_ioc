"""Reuse read-only Task06 attribution/failure helper with the Task08 loader."""

import importlib.util
import runpy
import sys
from pathlib import Path

path = Path(__file__).with_name("08-probe.py")
spec = importlib.util.spec_from_file_location("task08_probe", path)
if spec is None or spec.loader is None:
    raise RuntimeError("Missing Task08 probe")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
probe.install(sys.argv.pop(1))
sys.argv[0] = str(path.with_name("06-semantics.py"))
runpy.run_path(sys.argv[0], run_name="__main__")
