# ruff: noqa: E402, S101
"""Separate phase observer; segment high-water marks are not additive."""

import gc
import json
import sys
import tracemalloc

from source_loader import LOADED, install

install(sys.argv[1])
from clean_ioc import components, container

phases = []


def observe(label):
    current, peak = tracemalloc.get_traced_memory()
    phases.append({"phase": label, "current_bytes": current, "preceding_segment_peak_bytes": peak})
    tracemalloc.reset_peak()


def wrap(owner, name, predicate=lambda _: True):
    original = getattr(owner, name)

    def call(*args, **kwargs):
        if not predicate(args):
            return original(*args, **kwargs)
        observe(name + ":begin")
        result = original(*args, **kwargs)
        observe(name + ":end")
        return result

    setattr(owner, name, call)


for name in (
    "_expand_registration_templates",
    "_expand_decorator_templates",
    "_finalize_plan",
    "_compile_warmup_plans",
    "_retain_runtime_graph",
    "_reduce_explanation_metadata",
):
    wrap(container, name)
wrap(container._Compiler, "compile", lambda args: args[0]._profile_phase == "primary compilation")
wrap(components._ComponentGraph, "freeze", lambda args: len(args[0]._drafts) > 1000)
tracemalloc.start()
from benchmarks import graph_memory_fixture as fixture_module

observe("fixture:imported")
fixture = fixture_module.build(8, mode="run")
observe("build:return")
gc.collect()
observe("build:collected")
tracemalloc.stop()
print(json.dumps({"source": LOADED, "phases": phases}, indent=2))
fixture.runtime.__exit__(None, None, None)
