"""Can earlier cache release change a later callback's view of a derived value?"""

import importlib.util
import json
import sys
import weakref
from pathlib import Path

path = Path(__file__).with_name("06-probe.py")
spec = importlib.util.spec_from_file_location("task06_probe", path)
if spec is None or spec.loader is None:
    raise RuntimeError("Cannot load Task 06 probe module")
probe = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)
probe.install_probe(sys.argv[1] if len(sys.argv) > 1 else "baseline")

from clean_ioc import ContainerBuilder, derive  # noqa: E402

references = []
observations = []
calls = []


class Payload:
    pass


class Candidate:
    def __init__(self, value: Payload):
        self.value = value


class First:
    def __init__(self, values: list[Candidate]):
        self.values = values


class Later:
    def __init__(self, alive: bool):
        self.alive = alive


def make_value(context):
    calls.append("derive payload")
    value = Payload()
    references.append(weakref.ref(value))
    return value


def reject(component):
    calls.append("reject candidate")
    return False


def check_alive(context):
    calls.append("observe payload")
    result = bool(references and references[0]() is not None)
    observations.append(result)
    return result


builder = ContainerBuilder()
builder.register(Candidate, root_policy="dependency_only", arguments={"value": derive(make_value)}, when=reject)
builder.register(First)
builder.register(Later, arguments={"alive": derive(check_alive)})
with builder.build(explain_metadata=False, diagnostics=False, allow_scope_builders=False) as owner:
    result = {
        "probe": sys.argv[1] if len(sys.argv) > 1 else "baseline",
        "source": probe.evidence.source_provenance(),
        "calls": calls,
        "observations": observations,
        "resolved_argument": owner.resolve(Later).alive,
        "rejected_values": len(owner.resolve(First).values),
    }
print(json.dumps(result, indent=2, sort_keys=True))
