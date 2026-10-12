"""Exact runtime step-attribution census and failed-finalization probe."""

import argparse
import dataclasses
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, cast

path = Path(__file__).with_name("06-probe.py")
spec = importlib.util.spec_from_file_location("task06_probe", path)
if spec is None or spec.loader is None:
    raise RuntimeError("Cannot load Task 06 probe module")
probe = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)

from benchmarks.graph_memory_fixture import build  # noqa: E402
from clean_ioc import BuildIssue, ContainerBuilder, ContainerBuildError, IssueSeverity  # noqa: E402
from clean_ioc import container as runtime  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--probe", default="baseline")
parser.add_argument("--routes", type=int, default=2)
parser.add_argument("--full", action="store_true")
args = parser.parse_args()
probe.install_probe(args.probe)
fixture = build(args.routes, explain_metadata=args.full, allow_scope_builders=False)
plan = fixture.runtime._plan
pending: list[Any] = [
    root.step
    for groups in (plan.roots, plan.provider_roots, plan.managed_provider_roots)
    for roots in groups.values()
    for root in roots
]
seen = set()
counts = Counter()
helpers = (
    runtime._Step,
    runtime._CompiledDependency,
    runtime._CompiledDecorator,
    runtime._CompiledPreConfiguration,
    runtime._CompiledResolutionRequest,
)
while pending:
    item = pending.pop()
    if id(item) in seen:
        continue
    seen.add(id(item))
    if isinstance(item, (tuple, list)):
        pending.extend(item)
    elif isinstance(item, helpers):
        if isinstance(item, runtime._Step):
            component = getattr(item, "component", None)
            counts[(type(item).__name__, None if component is None else component.occurrence_id)] += 1
        pending.extend(getattr(item, field.name) for field in dataclasses.fields(cast(Any, item)))
result = {
    "probe": args.probe,
    "source": probe.evidence.source_provenance(),
    "probe_source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    "full": args.full,
    "source_attribution": sorted([[kind, occurrence, count] for (kind, occurrence), count in counts.items()], key=str),
    "physical_records": len(plan.graph._records or {}),
    "template_calls": fixture.callbacks_after_build,
}
if args.full:
    graph = fixture.runtime.graph
    result["manifest_fingerprint"] = graph.manifest(all_roots=True).fingerprint
    from uuid import UUID

    identities = {}

    def normalize(value):
        if isinstance(value, str):
            try:
                UUID(value)
            except ValueError:
                return value
            return identities.setdefault(value, f"identity:{len(identities)}")
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return tuple(map(normalize, value))
        return value

    facts = []
    for visit in graph.walk():
        component = visit.component
        if graph._component_evidence(graph._decorator_explanations, component) is None:
            continue
        explanation = graph.explain_decorators(component)
        facts.append(
            (
                component.occurrence_id,
                explanation.subject,
                normalize(tuple(dataclasses.asdict(item) for item in explanation.selected)),
                normalize(tuple(dataclasses.asdict(item) for item in explanation.rejected)),
            )
        )
    encoded = json.dumps(facts, sort_keys=True).encode()
    result["decorator_facts_sha256"] = hashlib.sha256(encoded).hexdigest()
    result["decorator_facts_count"] = len(facts)
fixture.runtime.__exit__(None, None, None)


class Service:
    pass


class Decorator:
    def __init__(self, inner: Service):
        self.inner = inner


builder = ContainerBuilder()
builder.register(Service)
builder.register_decorator(Service, Decorator)
builder.add_validation_rule(lambda _: [BuildIssue("refused", IssueSeverity.error, "refused")])
try:
    builder.build(diagnostics=False, explain_metadata=False)
except ContainerBuildError as error:
    graph = error.compiled_graph
    if graph is None:
        raise RuntimeError("Expected a complete final-validation graph")
    component = next(root.component for root in graph.roots if root.requested_type is Service)
    try:
        explanation = graph.explain_decorators(component)
        result["failed_finalization_decorator_facts"] = len(explanation.selected)
    except ValueError as missing:
        result["failed_finalization_decorator_facts"] = str(missing)
else:
    raise AssertionError("Expected final validation to reject the build")
print(json.dumps(result, indent=2, sort_keys=True))
