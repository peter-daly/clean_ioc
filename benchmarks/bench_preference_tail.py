"""Cost of an unreachable preference tail after a first-stage unique winner.

Reusable chains are constructed outside timing. Measure build and close against
the completed item 14 baseline, which omits the preference keyword.
"""

from typing import Any

from benchbro import Case

import clean_ioc
from clean_ioc import ContainerBuilder, Tag, select
from clean_ioc import component_filters as cf

_prefer = getattr(clean_ioc, "prefer", None)


def make_tail(length: int) -> Any:
    if _prefer is None:
        return None
    result = _prefer(cf.has_tag("primary"))
    for _ in range(length - 1):
        result = result.then(cf.all_components)
    return result


TAILS = {length: make_tail(length) for length in (1, 8, 64)}


class TailService:
    pass


class TailConsumer:
    def __init__(self, service: TailService):
        self.service = service


early_tail = Case(
    name="chained-preferences-early-tail",
    tags=["preferences", "build"],
    min_iterations=3,
    setup_timing="exclude",
    teardown_timing="exclude",
)


@early_tail.benchmark(name="first-stage-unique-16-candidates-8-parents")
@early_tail.parametrize("length", [1, 8, 64], ids=["1-stage", "8-stages", "64-stages"])
def first_stage_unique(length: int) -> None:
    builder = ContainerBuilder()
    for index in range(16):
        builder.register(TailService, tags=[Tag("primary")] if index == 0 else ())
    options = {"prefer": TAILS[length]} if _prefer is not None else {}
    for index in range(8):
        builder.register(
            TailConsumer,
            name=f"worker-{index}",
            arguments={"service": select(cf.all_components, **options)},
        )
    with builder.build():
        pass
