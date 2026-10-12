"""Reuse read-only Task06 attribution/failure helper with the Task09 loader."""

import contextlib
import importlib.util
import io
import json
import runpy
import sys
from pathlib import Path

path = Path(__file__).with_name("09-probe.py")
spec = importlib.util.spec_from_file_location("task09_probe", path)
if spec is None or spec.loader is None:
    raise RuntimeError("Missing Task09 probe")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
probe.install(sys.argv.pop(1))
sys.argv[0] = str(path.with_name("06-semantics.py"))
capture = io.StringIO()
with contextlib.redirect_stdout(capture):
    runpy.run_path(sys.argv[0], run_name="__main__")
result = json.loads(capture.getvalue())
result["loader_compatibility"] = probe.compatibility()
print(json.dumps(result, indent=2, sort_keys=True))
