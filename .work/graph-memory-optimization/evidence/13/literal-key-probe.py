# ruff: noqa: E402, S101, S603
"""Can mutable literal type labels expose weak callback dictionary comparisons?"""

import json
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from clean_ioc import ContainerBuilder, derive
from clean_ioc import container as code

policy = sys.argv[1]
if policy == "before":
    code._ActivationTemplateCache = dict  # ty: ignore[invalid-assignment]
elif policy == "superseded":
    code._activation_type_key_is_stable = lambda _: True  # ty: ignore[invalid-assignment]
calls = []
observations = []
rejections = 0


class Name(str):
    __hash__ = str.__hash__

    def __eq__(self, other):
        calls.append("name-equality")
        if rejections == 2:
            observations.append(True)
        return False


class Scalar(str):
    pass


Scalar.__module__ = Name("literal_metadata")
contract = Literal[Scalar("token")]  # ty: ignore[invalid-type-form]


class First:
    def __init__(self, values: list[contract]):
        self.values = values


class Second:
    def __init__(self, values: list[contract]):
        self.values = values


class Later:
    def __init__(self, count: int):
        self.count = count


class Wrapper:
    def __init__(self, inner: contract):
        self.inner = inner


def reject(component):
    global rejections
    rejections += 1
    calls.append("reject")
    Scalar.__module__ = "literal_metadata"
    return False


def observe(context):
    calls.append("observe")
    return bool(observations)


builder = ContainerBuilder().set_provider_roots(())
builder.register(contract, factory=lambda: "token", root_policy="dependency_only", when=reject)
builder.register_decorator(contract, Wrapper, when=lambda _: False)
builder.register(First)
builder.register(Second)
builder.register(Later, arguments={"count": derive(observe)})
with builder.build() as owner:
    result = {"policy": policy, "calls": calls, "resolved_argument": owner.resolve(Later).count}
print(json.dumps(result))
