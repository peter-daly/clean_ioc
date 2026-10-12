"""Real compiler before/after probes; baseline runs against the pinned item-14 tree.

Output files are created exclusively: baseline evidence cannot be overwritten.
"""

import argparse
import json
from itertools import permutations
from pathlib import Path

from clean_ioc import AsyncProvider, ContainerBuilder, ContainerBuildError, Provider, Tag, select
from clean_ioc import component_filters as cf


class Endpoint:
    pass


class A(Endpoint):
    pass


class B(Endpoint):
    pass


class C(Endpoint):
    pass


class Client:
    def __init__(self, endpoint: Endpoint):
        self.endpoint = endpoint


class Europe(Client):
    pass


class America(Client):
    pass


class Deferred:
    def __init__(self, endpoint: Provider[Endpoint]):
        self.endpoint = endpoint


class AsyncDeferred:
    def __init__(self, endpoint: AsyncProvider[Endpoint]):
        self.endpoint = endpoint


class Many:
    def __init__(self, endpoint: list[Endpoint]):
        self.endpoint = endpoint


def run(after):
    if after:
        from clean_ioc import prefer
    observations = []
    rows = []

    def chain(*predicates):
        if not after:
            return None
        result = None
        for index, predicate in enumerate(predicates):

            def observed(component, predicate=predicate, stage=index):
                value = bool(predicate(component))
                observations.append({"stage": stage, "candidate": component.implementation.__name__, "value": value})
                return value

            result = prefer(observed) if result is None else result.then(observed)
        return result

    def case(
        label,
        order,
        *,
        rules=None,
        consumer=None,
        filter=cf.all_components,
        clients=(Client,),
        metadata=None,
        precedence=None,
    ):
        observations.clear()
        builder = ContainerBuilder()
        metadata = metadata or {}
        for implementation in order:
            options = dict(metadata.get(implementation, {}))
            if after and rules and implementation in rules:
                options["prefer"] = chain(*rules[implementation])
            if precedence:
                options["parent_precedence"] = precedence.get(implementation, 0)
            builder.register(Endpoint, implementation, **options)
        policy = select(filter, **({"prefer": chain(*consumer)} if after and consumer else {}))
        for client in clients:
            tags = [Tag("workload", "batch"), Tag("region", "eu" if client is Europe else "us")]
            builder.register(client, arguments={"endpoint": policy}, tags=tags)
        row = {"id": label, "order": [item.__name__ for item in order]}
        try:
            with builder.build() as container:
                winners = {}
                for client in clients:
                    if client in (Deferred, AsyncDeferred):
                        # Frozen target edges are actual compiler output, independent of activation mode.
                        root = next(root for root in container.graph.roots if root.component.service_type is client)
                        winners[client.__name__] = (
                            root.component.dependencies[0].dependencies[0].implementation.__name__
                        )
                    else:
                        value = container.resolve(client).endpoint
                        winners[client.__name__] = (
                            [type(item).__name__ for item in value] if isinstance(value, list) else type(value).__name__
                        )
                row.update(
                    winners=winners,
                    root=type(container.resolve(Endpoint)).__name__,
                    warnings=[issue.code for issue in container.build_report.warnings],
                )
        except ContainerBuildError as error:
            row["error"] = [issue.code for issue in error.report.errors] if error.report else error.code
        row["observations"] = list(observations)
        row["callback_count"] = len(observations)
        rows.append(row)

    primary, eu, named = cf.has_tag("primary"), cf.has_tag("region", "eu"), cf.is_named
    metadata = {
        A: {"tags": [Tag("primary"), Tag("region", "eu")]},
        B: {"tags": [Tag("primary"), Tag("region", "us")]},
        C: {"tags": [Tag("region", "eu")]},
    }
    for order in permutations((A, B, C)):
        case("P1", order, consumer=(primary, eu), metadata=metadata)
        case(
            "P4",
            order,
            clients=(Europe, America),
            rules={
                A: (cf.parent(cf.has_tag("workload", "batch")), cf.parent(eu)),
                B: (cf.parent(cf.has_tag("workload", "batch")), cf.parent(cf.has_tag("region", "us"))),
            },
        )
    for order in permutations((A, B)):
        case("P2", order, consumer=(primary, eu), metadata={A: {"tags": [Tag("region", "eu")]}})
        case(
            "P3",
            order,
            consumer=(primary, eu, named),
            metadata={A: {"tags": [Tag("primary")]}, B: {"name": "named", "tags": [Tag("region", "eu")]}},
        )
        for client in (Deferred, AsyncDeferred):
            case("P5", order, clients=(client,), consumer=(cf.implementation_type_is(A),))
            case("P5-tie", order, clients=(client,), consumer=(cf.all_components,))
        case("P6-later", order, rules={A: ((lambda _: False), cf.all_components), B: ((lambda _: False),)})
        case(
            "P6-earlier",
            order,
            rules={A: (cf.all_components,), B: ((lambda _: False), cf.all_components, cf.all_components)},
        )
        case("P6-missing", order, rules={A: ((lambda _: False),)})
        case("G1", order, consumer=(cf.implementation_type_is(A),), filter=cf.implementation_type_is(B))
        case("G2", order, consumer=(cf.implementation_type_is(B),), rules={A: (cf.all_components,)})
        case(
            "G2-numeric",
            order,
            consumer=(cf.implementation_type_is(B),),
            rules={A: (cf.all_components,)},
            precedence={A: 10},
        )
        case(
            "G3",
            order,
            consumer=(named,),
            filter=cf.default_component_filter if hasattr(cf, "default_component_filter") else cf.is_not_named,
            metadata={B: {"name": "named"}},
        )
        case(
            "G4-collection",
            order,
            consumer=(cf.implementation_type_is(A),),
            rules={A: (cf.all_components,)},
            clients=(Many,),
        )
        case("C1-all-true", order, consumer=(cf.all_components,))
        case("C1-all-false", order, consumer=((lambda _: False),))
        case("C2-hard", order, consumer=(cf.implementation_type_is(B),), filter=cf.implementation_type_is(A))
        case("C2-numeric", order, consumer=(cf.implementation_type_is(B),), precedence={A: 1})
        case("R1-prefix", order, consumer=(cf.implementation_type_is(A),))
        case("R1-extended", order, consumer=(cf.implementation_type_is(A), cf.implementation_type_is(B)))
        case("R2", order, rules={A: (cf.all_components,)})
    case("C1-single", (A,), consumer=((lambda _: False),))
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("before", "after"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rows = run(args.phase == "after")
    with args.output.open("x") as stream:
        json.dump({"phase": args.phase, "rows": rows}, stream, indent=2)
        stream.write("\n")
