"""Real compiler G4/G5 controls against the same pinned baseline as primary probes."""

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from clean_ioc import BoundaryAlias, ContainerBuilder, ContainerBuildError, Expose, Provider, select
from clean_ioc import component_filters as cf


class Policy:
    pass


class A(Policy):
    pass


class B(Policy):
    pass


class Client:
    def __init__(self, policy: Policy):
        self.policy = policy


class Deferred:
    def __init__(self, policy: Provider[Policy]):
        self.policy = policy


class Frozen(Client):
    pass


class Public:
    pass


class PublicClient:
    def __init__(self, policy: Public):
        self.policy = policy


def run(after):
    calls = []
    rows = []
    if after:
        from clean_ioc import prefer

    def options(predicate=cf.all_components):
        if not after:
            return {}

        def observed(component):
            value = bool(predicate(component))
            calls.append(
                {
                    "candidate": component.implementation.__name__
                    if component.implementation in (A, B)
                    else "instance-B",
                    "parent": str(component.parent.service_type) if component.parent else None,
                    "value": value,
                }
            )
            return value

        return {"prefer": prefer(observed)}

    def record(label, build):
        calls.clear()
        row = {"id": label}
        try:
            row["result"] = build()
        except ContainerBuildError as error:
            row["errors"] = [issue.code for issue in error.report.errors] if error.report else [error.code]
        row["observations"] = list(calls)
        row["callback_count"] = len(calls)
        rows.append(row)

    def maps(duplicate=False):
        builder = ContainerBuilder()
        builder.register(Policy, A, **options())
        builder.register(Policy, B, **options())
        builder.register_provider_map(
            Policy, key=(lambda _: "same") if duplicate else (lambda c: c.implementation.__name__)
        )
        with builder.build() as container:
            mapping = container.resolve(Mapping[str, Provider[Policy]])
            return {"members": list(mapping), "values": [type(value()).__name__ for value in mapping.values()]}

    record("G4-provider-map", maps)
    record("G4-duplicate-key", lambda: maps(True))

    def boundary(duplicate=False, alias=False):
        builder = ContainerBuilder()
        source = builder.create_boundary(
            "source", exposes=(Expose(Policy, alias=BoundaryAlias(Public, name="public") if alias else None),)
        )
        source.register(Policy, A, **options())
        if duplicate:
            source.register(Policy, B)
        builder.register(Public if alias else Policy, instance=cast(Any, B()))
        builder.register(
            PublicClient if alias else Client,
            arguments={"policy": select(cf.all_components, **options(cf.is_named))} if alias else None,
        )
        with builder.build() as container:
            value = container.resolve(PublicClient if alias else Client)
            return type(value.policy).__name__

    record("G4-boundary-cardinality", lambda: boundary(True))
    record("G5-boundary-mask", boundary)
    record("G5-alias-public-view", lambda: boundary(alias=True))

    def provider(nested=False):
        builder = ContainerBuilder()
        predicate = (
            cf.parent(cf.parent(cf.service_type_is(Deferred))) if nested else cf.parent(cf.service_type_is(Deferred))
        )
        builder.register(Policy, A, **options(predicate))
        builder.register(Policy, B)
        builder.register(Deferred)
        with builder.build() as container:
            return type(container.resolve(Deferred).policy()).__name__

    record("G5-provider-immediate", provider)
    record("G5-provider-nested", lambda: provider(True))

    def overlay():
        builder = ContainerBuilder()
        builder.register(Policy, A, lifespan="singleton", **options())
        builder.register(Policy, B, lifespan="singleton")
        builder.register(Frozen, lifespan="singleton")
        builder.register(Client)
        with builder.build() as parent:
            original = parent.resolve(Frozen)
            child = parent.new_scope_builder()
            child.register(Policy, B, lifespan="singleton", parent_precedence=1)
            with child.build() as scope:
                before = len(calls)
                result = {
                    "original": type(original.policy).__name__,
                    "anchored_same": scope.resolve(Frozen) is original,
                    "new": type(scope.resolve(Client).policy).__name__,
                }
                result["runtime_callback_count"] = len(calls) - before
                return result

    record("G5-overlay", overlay)
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("before", "after"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with args.output.open("x") as stream:
        json.dump({"phase": args.phase, "rows": run(args.phase == "after")}, stream, indent=2)
        stream.write("\n")
