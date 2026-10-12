"""Record actual LIFO outcomes for work item 14; no proposed scoring is run.

Run from the repository root with:
    PYTHONPATH=. uv run python .work/probes/parent_filter_baseline.py

The examples use existing public APIs. Names describe illustrative policies,
not a dependency on Bark Core. The JSON is design evidence, not a new scoring
implementation or a test asserting that LIFO must remain forever.
"""

import json
from dataclasses import dataclass
from itertools import permutations
from typing import Any

from clean_ioc import ComponentFilter, ContainerBuilder, ContainerBuildError, Provider, Tag, select
from clean_ioc import component_filters as cf


class WaitPolicy:
    pass


class DefaultWait(WaitPolicy):
    pass


class OrdersWait(WaitPolicy):
    pass


class BatchWait(WaitPolicy):
    pass


class EuropeanBatchWait(WaitPolicy):
    pass


class EuropeWait(WaitPolicy):
    pass


class AmericaWait(WaitPolicy):
    pass


class PrivateWait(WaitPolicy):
    pass


class ApplicationWait(WaitPolicy):
    pass


class Worker:
    def __init__(self, policy: WaitPolicy, policies: list[WaitPolicy]):
        self.policy = policy
        self.policies = policies


class ProviderWorker:
    def __init__(self, policy: Provider[WaitPolicy]):
        self.policy = policy


@dataclass(frozen=True)
class Rule:
    implementation: type[WaitPolicy]
    when: ComponentFilter = cf.all_components


@dataclass(frozen=True)
class Parent:
    name: str
    tags: tuple[Tag, ...] = ()


def observe(
    rules: tuple[Rule, ...],
    parents: tuple[Parent, ...],
    *,
    consumer_filter: ComponentFilter | None = None,
) -> dict[str, Any]:
    builder = ContainerBuilder()
    for rule in rules:
        builder.register(WaitPolicy, rule.implementation, when=rule.when)
    for parent in parents:
        builder.register(
            Worker,
            name=parent.name,
            tags=parent.tags,
            arguments=None if consumer_filter is None else {"policy": select(consumer_filter)},
        )
    preview_id = builder.get_component_id(WaitPolicy)
    with builder.build() as container:
        observations = {}
        for parent in parents:
            worker = container.resolve(Worker, filter=cf.with_name(parent.name))
            observations[parent.name] = {
                "single": type(worker.policy).__name__,
                "collection": [type(policy).__name__ for policy in worker.policies],
            }
        # Parentless root candidates may be empty for exclusively contextual rules.
        roots = container.resolve(list[WaitPolicy], filter=cf.all_components)
        root_winner = type(container.resolve(WaitPolicy)).__name__ if roots else None
        return {
            "registration_order_oldest_first": [rule.implementation.__name__ for rule in rules],
            "parents": observations,
            "parentless_root": root_winner,
            "parentless_preview_found": preview_id is not None,
            "warning_codes": sorted({issue.code for issue in container.build_report.warnings}),
        }


def permutation_case(
    case_id: str,
    rules: tuple[Rule, ...],
    parents: tuple[Parent, ...],
    desired: dict[str, str],
) -> dict[str, Any]:
    runs = [observe(tuple(order), parents) for order in permutations(rules)]
    satisfied = sum(
        all(run["parents"][name]["single"] == implementation for name, implementation in desired.items())
        for run in runs
    )
    return {
        "case": case_id,
        "desired_single_winners": desired,
        "baseline_permutations_satisfying_all_desired_winners": satisfied,
        "permutations": len(runs),
        "observed_before": runs,
    }


def provider_case(*, target_worker_through_provider: bool) -> dict[str, Any]:
    builder = ContainerBuilder()
    orders = cf.parent(cf.with_name("orders"))
    rule = cf.parent(orders) if target_worker_through_provider else orders
    case_id = "P3" if target_worker_through_provider else "G3"
    builder.register(WaitPolicy, OrdersWait, when=rule)
    builder.register(WaitPolicy, DefaultWait)
    builder.register(ProviderWorker, name="orders")
    try:
        with builder.build() as container:
            worker = container.resolve(ProviderWorker, filter=cf.with_name("orders"))
            return {"case": case_id, "build": "succeeded", "provider_target": type(worker.policy()).__name__}
    except ContainerBuildError as error:
        codes = sorted({i.code for i in error.report.errors}) if error.report is not None else [error.code]
        return {"case": case_id, "build": "failed", "error_codes": codes}


def main() -> None:
    orders = cf.parent(cf.with_name("orders"))
    batch = cf.has_tag("workload", "batch")
    europe = cf.has_tag("region", "eu")
    parents = (Parent("orders"), Parent("invoices"))
    cases = [
        permutation_case(
            "P1",
            (Rule(DefaultWait), Rule(OrdersWait, orders)),
            parents,
            {"orders": "OrdersWait", "invoices": "DefaultWait"},
        ),
        permutation_case(
            "P2",
            (
                Rule(DefaultWait),
                Rule(BatchWait, cf.parent(batch)),
                Rule(EuropeanBatchWait, cf.parent(batch & europe)),
            ),
            (
                Parent("eu-batch", (Tag("workload", "batch"), Tag("region", "eu"))),
                Parent("us-batch", (Tag("workload", "batch"), Tag("region", "us"))),
                Parent("interactive"),
            ),
            {"eu-batch": "EuropeanBatchWait", "us-batch": "BatchWait", "interactive": "DefaultWait"},
        ),
        provider_case(target_worker_through_provider=True),
        permutation_case(
            "C1",
            (
                Rule(EuropeWait, cf.parent(europe)),
                Rule(AmericaWait, cf.parent(cf.has_tag("region", "us"))),
            ),
            (Parent("europe", (Tag("region", "eu"),)), Parent("america", (Tag("region", "us"),))),
            {"europe": "EuropeWait", "america": "AmericaWait"},
        ),
        permutation_case(
            "C2",
            (Rule(DefaultWait, ~orders), Rule(OrdersWait, orders)),
            parents,
            {"orders": "OrdersWait", "invoices": "DefaultWait"},
        ),
        {
            "case": "C3",
            "observed_before": [
                observe(tuple(order), (Parent("orders"),))
                for order in permutations((Rule(OrdersWait, orders), Rule(ApplicationWait, orders)))
            ],
        },
        {
            "case": "G1",
            "observed_before": observe(
                (Rule(DefaultWait), Rule(OrdersWait, orders)),
                parents,
                consumer_filter=cf.implementation_type_is(DefaultWait),
            ),
        },
        {
            "case": "G2",
            "observed_before": [
                observe(tuple(order), parents)
                for order in permutations((Rule(DefaultWait), Rule(OrdersWait, orders | cf.parent(orders))))
            ],
        },
        provider_case(target_worker_through_provider=False),
        {
            "case": "R1",
            "observed_before": observe((Rule(OrdersWait, orders), Rule(ApplicationWait)), (Parent("orders"),)),
        },
        {
            "case": "R2",
            "observed_before": [
                observe(tuple(order), (Parent("private-eu", (Tag("region", "eu"), Tag("privacy", "restricted"))),))
                for order in permutations(
                    (
                        Rule(EuropeWait, cf.parent(europe)),
                        Rule(PrivateWait, cf.parent(cf.has_tag("privacy", "restricted"))),
                    )
                )
            ],
        },
    ]
    print(
        json.dumps({"evidence": "Executed baseline only; after outcomes are design targets", "cases": cases}, indent=2)
    )


if __name__ == "__main__":
    main()
