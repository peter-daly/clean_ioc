"""Task06's 16 lifetime witnesses, adapted only to task10's private historical API."""

# ruff: noqa: S101, S102
import contextlib
import hashlib
import io
import json
import sys
from pathlib import Path

path = Path(__file__).parent.parent / "06-value-kinds.py"
source = path.read_text()
assert source.count("builder.build(") == 1
source = source.replace("builder.build(", "builder._build(")
sys.argv = [str(path), "baseline"]
output = io.StringIO()
with contextlib.redirect_stdout(output):
    exec(compile(source, str(path), "exec"), {"__file__": str(path), "__name__": "__main__"})
result = json.loads(output.getvalue())
assert len(result["cases"]) == 16
assert all(case["resolved_argument"] for case in result["cases"])
result["task15_adapter"] = "Only build to _build spelling changed; no task06 cache patch installed."
result["original_script_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
print(json.dumps(result, indent=2))
