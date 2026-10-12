"""Cache-only observer, separate from timing/peak comparisons."""

import argparse
import json
import sys
import weakref
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmarks.graph_memory_evidence import census, source_provenance
from benchmarks.graph_memory_fixture import build
from clean_ioc import container as runtime

parser = argparse.ArgumentParser()
parser.add_argument("--weak", action="store_true")
args = parser.parse_args()
observations = []
base: Any = weakref.WeakValueDictionary if args.weak else dict


class Cache(base):
    def __init__(self, facts):
        super().__init__()
        self.facts = facts

    def get(self, key, default=None):
        result = super().get(key, default)
        self.facts["misses" if result is None else "hits"] += 1
        return result

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.facts["insertions"] += 1
        self.facts["maximum_live_entries"] = max(self.facts["maximum_live_entries"], len(self))


original_init = runtime._Compiler.__init__
original_compile = runtime._Compiler.compile


def init(compiler, *args, **kwargs):
    original_init(compiler, *args, **kwargs)
    facts = dict(phase=compiler._profile_phase, hits=0, misses=0, insertions=0, maximum_live_entries=0)
    observations.append(facts)
    compiler._activation_templates = Cache(facts)


def compile_plan(compiler, *args, **kwargs):
    result = original_compile(compiler, *args, **kwargs)
    cache = compiler._activation_templates
    cache.facts["entries_at_compile_return"] = len(cache)
    cache.facts["graph_drafts_at_compile_return"] = len(compiler.graph._drafts)
    return result


runtime._Compiler.__init__ = init
runtime._Compiler.compile = compile_plan
fixture = build(8, diagnostics=False, explain_metadata=False, allow_scope_builders=False)
result = {
    "source": source_provenance(),
    "weak": args.weak,
    "observations": observations,
    "graph": census(fixture.runtime),
    "template_calls": fixture.callbacks_after_build,
}
fixture.runtime.__exit__(None, None, None)
print(json.dumps(result, indent=2, sort_keys=True))
