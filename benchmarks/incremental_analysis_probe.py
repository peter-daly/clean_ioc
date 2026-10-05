"""Item 18 investigation only; no supported cache API or runtime integration.

The conservative candidate replaces name validation in this isolated experiment.
The unsafe ceiling omits that validation entirely to estimate its maximum cost.
All other build work, callbacks, declarations and normal close remain included.
Never use the ceiling for application compilation. Do not run patch contexts in
parallel; cache lookup concurrency and compiler integration are separate issues.
"""

import inspect
import types
from collections import Counter, OrderedDict
from collections.abc import Mapping
from contextlib import contextmanager
from threading import RLock
from typing import Any
from unittest.mock import patch

from benchbro import Case

from benchmarks.bench_compiler_optimization import build_inputs, make_builder
from clean_ioc import container as compiler

ORIGINAL = compiler._validate_dependency_names
SIGNATURE_CONTROLS = frozenset(("__signature__", "__wrapped__", "__text_signature__", "__partialmethod__"))
# Exact builtin types are intentional eligibility guards, excluding overrides.
# ruff: noqa: E721


class ParameterShapeProbe:
    """Bounded experiment storing argument shapes, never application objects."""

    def __init__(self, limit: int = 128):
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        self.limit = limit
        self.entries: OrderedDict[tuple, tuple[frozenset[str], bool]] = OrderedDict()
        self.counts: Counter[str] = Counter()
        self.lock = RLock()

    def clear(self):
        with self.lock:
            self.entries.clear()

    def _key(self, implementation: Any):
        # Reject aliases and arbitrary callable objects before traversing any
        # attributes. Their normalization/descriptor evaluation belongs only
        # to the original path, exactly once.
        if type(implementation) not in (type, types.FunctionType):
            return None, "nonstandard callable"
        subject = implementation
        drop_first = False
        if type(subject) is type:
            if any(any(type(name) is not str for name in vars(base)) for base in subject.__mro__):
                return None, "nonstandard namespace"
            if any("__new__" in vars(base) for base in subject.__mro__ if base is not object):
                return None, "custom constructor"
            if any(SIGNATURE_CONTROLS.intersection(vars(base)) for base in subject.__mro__ if base is not object):
                return None, "signature control"
            subject = next(vars(base)["__init__"] for base in subject.__mro__ if "__init__" in vars(base))
            drop_first = True
        if type(subject) is not types.FunctionType:
            return None, "nonstandard callable"
        if type(subject.__dict__) is not dict or any(type(name) is not str for name in subject.__dict__):
            return None, "nonstandard namespace"
        if SIGNATURE_CONTROLS.intersection(subject.__dict__):
            return None, "signature control"
        if getattr(subject, "__annotate__", None) is not None:
            return None, "deferred annotations"
        annotations = subject.__annotations__
        defaults = subject.__defaults__
        keyword_defaults = subject.__kwdefaults__
        if type(annotations) is not dict or any(type(name) is not str for name in annotations):
            return None, "nonstandard annotations"
        if defaults is not None and type(defaults) is not tuple:
            return None, "nonstandard defaults"
        if keyword_defaults is not None and (
            type(keyword_defaults) is not dict or any(type(name) is not str for name in keyword_defaults)
        ):
            return None, "nonstandard defaults"
        code = subject.__code__
        variadic_flags = code.co_flags & (inspect.CO_VARARGS | inspect.CO_VARKEYWORDS)
        count = code.co_argcount + code.co_kwonlyargcount
        count += bool(variadic_flags & inspect.CO_VARARGS) + bool(variadic_flags & inspect.CO_VARKEYWORDS)
        names = code.co_varnames[:count]
        if any(type(name) is not str for name in names):
            return None, "nonstandard parameter names"
        return (
            names,
            code.co_argcount,
            code.co_posonlyargcount,
            code.co_kwonlyargcount,
            variadic_flags,
            drop_first,
            0 if defaults is None else len(defaults),
            () if keyword_defaults is None else tuple(sorted(keyword_defaults)),
        ), None

    def validate(self, implementation: Any, dependencies: Mapping[str, Any]) -> None:
        if type(dependencies) is not dict or any(type(name) is not str for name in dependencies):
            with self.lock:
                self.counts["rejected: nonstandard dependencies"] += 1
            return ORIGINAL(implementation, dependencies)
        key, rejection = self._key(implementation)
        if key is None:
            with self.lock:
                self.counts[f"rejected: {rejection}"] += 1
            return ORIGINAL(implementation, dependencies)
        with self.lock:
            shape = self.entries.get(key)
            if shape is not None:
                self.entries.move_to_end(key)
                self.counts["hits"] += 1
            else:
                self.counts["misses"] += 1
                try:
                    parameters = inspect.signature(implementation).parameters
                except (TypeError, ValueError):
                    self.counts["signature failures"] += 1
                    return
                shape = (
                    frozenset(parameters),
                    any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()),
                )
                self.entries[key] = shape
                if len(self.entries) > self.limit:
                    self.entries.popitem(last=False)
                    self.counts["evictions"] += 1
        names, arbitrary_keywords = shape
        if not arbitrary_keywords and set(dependencies) - names:
            # Reuse only successful name membership. The original diagnostic
            # path provides exactly the current qualified name and exception.
            return ORIGINAL(implementation, dependencies)


@contextmanager
def investigation(mode: str, probe: ParameterShapeProbe):
    if mode == "candidate":
        validator = probe.validate
    elif mode == "unsafe-ceiling":
        validator = _unsafe_ceiling
    elif mode not in ("full", "full-repeat"):
        raise ValueError(mode)
    else:
        validator = ORIGINAL
    with patch.object(compiler, "_validate_dependency_names", validator):
        yield


def _unsafe_ceiling(implementation: Any, dependencies: Mapping[str, compiler.legacy.Dependency]) -> None:
    pass


# Warm cache across fresh builders, without application activation or values.
PROBE = ParameterShapeProbe()
SHAPES = ("wide-24", "generic-8-roots", "collection-12", "template-12", "managed-warmup")
MODES = ("full", "candidate", "unsafe-ceiling", "full-repeat")
case = Case(name="incremental-name-analysis-investigation", tags=["incremental-investigation"], min_iterations=8)


@case.benchmark(name="fresh-declaration-build")
@case.parametrize("mode", MODES)
@case.parametrize("shape", SHAPES)
def fresh_build(shape: str, mode: str):
    with investigation(mode, PROBE):
        with make_builder(shape).build(**build_inputs(shape)):
            pass
