"""Isolate across-build reuse from the same probe's within-build hits.

Fresh declarations/build/close remain measured. Clearing an already-owned probe
before each build is included, slightly favoring warm reuse. A warm repeat is an
unchanged drift control. Only two original representative shapes are selected.
"""

from benchbro import Case

from benchmarks.bench_compiler_optimization import build_inputs, make_builder
from benchmarks.incremental_analysis_probe import ParameterShapeProbe, investigation

PROBE = ParameterShapeProbe()
case = Case(name="incremental-analysis-lifetime", tags=["incremental-investigation"], min_iterations=8)


@case.benchmark(name="fresh-declaration-build")
@case.parametrize("mode", ("warm", "cleared-per-build", "warm-repeat"))
@case.parametrize("shape", ("generic-8-roots", "collection-12"))
def fresh_build(shape: str, mode: str):
    if mode == "cleared-per-build":
        PROBE.clear()
    with investigation("candidate", PROBE):
        with make_builder(shape).build(**build_inputs(shape)):
            pass
