"""Prepare inert transformed sources before all measured processes."""

import hashlib
import importlib.util
import json
import marshal
import sys
from pathlib import Path

path = Path(__file__).with_name("07-probe.py")
spec = importlib.util.spec_from_file_location("task07_probe", path)
if spec is None or spec.loader is None:
    raise RuntimeError("Missing Task07 probe")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
source = (probe.ROOT / "clean_ioc/container.py").read_text()
result = {
    "original_sha256": hashlib.sha256(source.encode()).hexdigest(),
    "transformed_sha256": {},
    "bytecode_sha256": {},
}
for name in ("baseline", "slots", "prelookup", "indexes"):
    changed = probe.transform(source, name)
    path.with_name(f"07-{name}-container.py.txt").write_text(changed)
    result["transformed_sha256"][name] = hashlib.sha256(changed.encode()).hexdigest()
    payload = marshal.dumps(compile(changed, str(probe.ROOT / "clean_ioc/container.py"), "exec"))
    path.with_name(f"07-{name}-{sys.implementation.cache_tag}-container.code.bin").write_bytes(payload)
    result["bytecode_sha256"][name] = hashlib.sha256(payload).hexdigest()
path.with_name("07-prepared-sources.json").write_text(json.dumps(result, indent=2) + "\n")
