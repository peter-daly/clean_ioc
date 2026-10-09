"""Item 20 experiment, deliberately excluded from ordinary bench_* discovery.

Run with --case compilation-budgets and explicit /tmp report paths. Importing the
stable fixture module also registers its cases; the explicit case filter isolates
this experiment. Build-only iteration fixtures exclude declarations/normal close.
Budget objects are prepared at import, outside measurement. Failure includes safe
report capture; no constructors, providers or warm-up targets are activated.
"""

from collections.abc import Iterator

from benchbro import Case, system

from benchmarks import bench_compiler_optimization as fixtures
from clean_ioc import CompilationBudget, ContainerBuildError

MODES = ("none", "unlimited", "generous", "bounded")
BUDGETS = {
    "none": None,
    "unlimited": CompilationBudget(),
    "generous": CompilationBudget(
        graph_occurrences=100_000,
        active_dependency_depth=100,
        specialization_materializations=10_000,
        generated_template_outputs=10_000,
        diagnostic_attempts=100,
        preparation_operations=100_000,
    ),
    "bounded": CompilationBudget(graph_occurrences=100),
}

case = Case(
    name="compilation-budgets",
    tags=["compilation-budgets", "build"],
    min_iterations=8,
    setup_timing="exclude",
    teardown_timing="exclude",
)


def compile_prepared(prepared: dict, mode: str) -> None:
    try:
        prepared["owner"] = prepared["builder"].build(budget=BUDGETS[mode], **prepared["inputs"])
    except ContainerBuildError as error:
        if mode != "bounded" or error.report is None or error.report.errors[-1].code != "compilation-budget-exceeded":
            raise
        if error.compiled_graph is not None:
            raise AssertionError("Exhaustion exposed a compiled graph")


@system(scope="iteration")
def budget_wide():
    yield from fixtures.prepared_build("wide-24")


@case.benchmark(name="wide-24")
@case.parametrize("mode", MODES)
def wide(budget_wide, mode: str):
    compile_prepared(budget_wide, mode)


@system(scope="iteration")
def budget_generic():
    yield from fixtures.prepared_build("generic-8-roots")


@case.benchmark(name="generic-8-roots")
@case.parametrize("mode", MODES)
def generic(budget_generic, mode: str):
    compile_prepared(budget_generic, mode)


@system(scope="iteration")
def budget_collection():
    yield from fixtures.prepared_build("collection-12")


@case.benchmark(name="collection-12")
@case.parametrize("mode", MODES)
def collection(budget_collection, mode: str):
    compile_prepared(budget_collection, mode)


@system(scope="iteration")
def budget_template():
    yield from fixtures.prepared_build("template-12")


@case.benchmark(name="template-12")
@case.parametrize("mode", MODES)
def template(budget_template, mode: str):
    compile_prepared(budget_template, mode)


@system(scope="iteration")
def budget_overlay() -> Iterator[dict]:
    builder = fixtures.make_builder("managed-warmup")
    # Parent ownership and compilation are outside the measured overlay build.
    parent = builder.build()
    prepared = {"builder": parent.new_scope_builder(), "inputs": {}, "owner": None}
    try:
        yield prepared
    finally:
        if prepared["owner"] is not None:
            prepared["owner"].__exit__()
        parent.__exit__()


@case.benchmark(name="overlay")
@case.parametrize("mode", MODES)
def overlay(budget_overlay, mode: str):
    compile_prepared(budget_overlay, mode)
