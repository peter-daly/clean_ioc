"""Intrusive allocation/liveness census, never used for timing or memory claims."""

import gc
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure import sample

from clean_ioc import ContainerBuilder
from clean_ioc import container as code

counts = {name: Counter() for name in ("CandidateDecision", "TemplateDecision")}
exact, payloads = set(), set()
pools = []


def observe_type(name):
    cls = getattr(code, name)
    original = cls.__init__

    def init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        if type(self) is not cls:
            return
        count = counts[name]
        count["constructed"] += 1
        count["live"] += 1
        count["maximum_live"] = max(count["maximum_live"], count["live"])
        if name == "TemplateDecision":
            values = tuple(getattr(self, field) for field in self.__dataclass_fields__)
            exact.add(values)
            payloads.add(
                tuple(
                    value for field, value in zip(self.__dataclass_fields__, values) if field != "target_occurrence_id"
                )
            )

    def delete(self):
        if type(self) is cls:
            counts[name]["live"] -= 1

    cls.__init__ = init
    cls.__del__ = delete


for name in counts:
    observe_type(name)


def compiler_deleted(self):
    names = ("_decorator_template_facts", "_decorator_rejections", "_decorator_patterns")
    pools.append(
        {
            name: {
                "entries": len(getattr(self, name, {})),
                "dict_bytes": sys.getsizeof(getattr(self, name, {})),
                "key_bytes": sum(sys.getsizeof(key) for key in getattr(self, name, {})),
                "identity_key_member_bytes": (
                    sum({id(part): sys.getsizeof(part) for key in getattr(self, name, {}) for part in key}.values())
                    if name == "_decorator_template_facts"
                    else 0
                ),
                "entry_tuple_bytes": (
                    sum(sys.getsizeof(value) for value in getattr(self, name, {}).values())
                    if name == "_decorator_template_facts"
                    else 0
                ),
                "identity_owner_tuple_bytes": (
                    sum(sys.getsizeof(value[0]) for value in getattr(self, name, {}).values())
                    if name == "_decorator_template_facts"
                    else 0
                ),
            }
            for name in names
        }
    )


setattr(code._Compiler, "__del__", compiler_deleted)
original_build = ContainerBuilder.build
retained = []


def build(self, **kwargs):
    runtime = original_build(self, **kwargs)
    gc.collect()
    retained.append({name: dict(value) for name, value in counts.items()})
    return runtime


ContainerBuilder.build = build
result = sample(sys.argv[1], False)
gc.collect()
print(
    json.dumps(
        {
            "source": result["source"],
            "variant": sys.argv[1],
            "counts": counts,
            "after_build": retained,
            "exact_template_signatures": len(exact),
            "template_payload_signatures_without_occurrence": len(payloads),
            "compiler_pools_at_release": pools,
        },
        indent=2,
    )
)
