"""Bounded, stable-schema compiler workloads for work items 18-20.

Definitions and generic aliases are created at module import, outside timing.
Declaration+build includes declarations, build and normal close. Build-only uses
iteration fixtures: fresh declarations and parent owners are excluded, build is
measured, normal close is excluded. Related batches use fresh single-use builders.
No compilation benchmark activates application objects. Matrix includes its
normal manifest/report work and close; it is a separate end-to-end question.
"""

from collections.abc import Iterator
from typing import Any, Generic, TypeVar

from benchbro import Case, system

from clean_ioc import (
    ContainerBuilder,
    ManagedProvider,
    RegistrationTemplate,
    WarmupPlan,
    WarmupTarget,
    build_arg,
    select,
)
from clean_ioc import component_filters as cf
from clean_ioc.matrix import BuildMatrix, BuildVariant

ACTIVATIONS = 0
T = TypeVar("T")


def activated() -> None:
    global ACTIVATIONS
    ACTIVATIONS += 1


class Leaf:
    def __init__(self):
        activated()


class Setting:
    def __init__(self, value: int):
        activated()
        self.value = value


class GenericLeaf(Generic[T]):
    def __init__(self):
        activated()


class GenericBranch(Generic[T]):
    def __init__(self, left: GenericLeaf[T], right: GenericLeaf[T]):
        activated()
        self.left, self.right = left, right


def branch(left: GenericLeaf[T], right: GenericLeaf[T]) -> GenericBranch[T]:
    return GenericBranch(left, right)


def node(name: str, dependencies: dict[str, Any]) -> type:
    if "setting" in dependencies:

        def init(self, left, right, setting):
            activated()
            self.left, self.right, self.setting = left, right, setting
    else:

        def init(self, left, right):
            activated()
            self.left, self.right = left, right

    init.__annotations__ = {**dependencies, "return": None}

    return type(name, (), {"__init__": init, "__module__": __name__})


WIDE = tuple(type(f"WideLeaf{i}", (Leaf,), {"__module__": __name__}) for i in range(24))
DIAMOND = [Leaf]
for level in range(1, 6):
    DIAMOND.append(node(f"Diamond{level}", {"left": DIAMOND[-1], "right": DIAMOND[-1]}))
GENERIC_KEYS = (int, str, float, bytes)
GENERIC_ROOTS = tuple(
    node(f"GenericConsumer{i}", {"left": GenericBranch[key], "right": GenericBranch[key], "setting": Setting})
    for i, key in enumerate(GENERIC_KEYS * 2)
)


class Worker:
    def __init__(self, source: Leaf):
        activated()
        self.source = source


class CollectionRoot:
    def __init__(self, workers: list[Worker]):
        activated()
        self.workers = workers


class CompatibilityRoot:
    def __init__(self, managed: ManagedProvider[Leaf], leaf: Leaf):
        activated()
        self.managed, self.leaf = managed, leaf


def resource() -> Iterator[Leaf]:
    yield Leaf()


SHAPES = ("wide-24", "diamond-depth-5", "generic-8-roots", "collection-12", "template-12", "managed-warmup")


def make_builder(shape: str, *, parent=None):
    builder = ContainerBuilder() if parent is None else parent.new_scope_builder()
    if shape == "wide-24":
        for service in WIDE:
            builder.register(service)
    elif shape == "diamond-depth-5":
        for service in DIAMOND:
            builder.register(service, root_policy="resolvable" if service is DIAMOND[-1] else "dependency_only")
    elif shape == "generic-8-roots":
        builder.register(Setting, arguments={"value": build_arg("setting")}, root_policy="dependency_only")
        for key in GENERIC_KEYS:
            builder.register(GenericLeaf[key], root_policy="dependency_only")
        builder.register(GenericBranch, factory=branch, root_policy="dependency_only")
        for service in GENERIC_ROOTS:
            builder.register(service)
    elif shape in ("collection-12", "template-12"):
        ids = [builder.register(Leaf, lifespan="singleton", root_policy="dependency_only") for _ in range(12)]
        if shape == "template-12":
            builder.register_registration_template(
                for_each=Leaf,
                template=lambda source: RegistrationTemplate(
                    Worker, arguments={"source": select(cf.with_id(source.id))}, root_policy="dependency_only"
                ),
            )
        else:
            for source_id in ids:
                builder.register(
                    Worker, arguments={"source": select(cf.with_id(source_id))}, root_policy="dependency_only"
                )
        builder.register(CollectionRoot)
    elif shape == "managed-warmup":
        builder.register(Leaf, factory=resource, lifespan="singleton")
        builder.register(CompatibilityRoot)
        builder.add_warmup_plan(WarmupPlan("startup", [WarmupTarget(Leaf)]))
    else:
        raise ValueError(shape)
    return builder


def build_inputs(shape: str, setting: int = 1) -> dict:
    return {"build_args": {"setting": setting}} if shape == "generic-8-roots" else {}


declarations = Case(name="compiler-declaration-build", tags=["compiler-optimization", "build"], min_iterations=8)


@declarations.benchmark(name="fresh")
@declarations.parametrize("shape", SHAPES)
def declaration_build(shape: str):
    with make_builder(shape).build(**build_inputs(shape)):
        pass


def prepared_build(shape: str) -> Iterator[dict]:
    prepared = {"builder": make_builder(shape), "inputs": build_inputs(shape), "owner": None}
    try:
        yield prepared
    finally:
        if prepared["owner"] is not None:
            prepared["owner"].__exit__()


compilation = Case(
    name="compiler-build-only",
    tags=["compiler-optimization", "build"],
    min_iterations=8,
    setup_timing="exclude",
    teardown_timing="exclude",
)


def compile_prepared(prepared: dict):
    prepared["owner"] = prepared["builder"].build(**prepared["inputs"])


@system(scope="iteration")
def prepared_wide():
    yield from prepared_build("wide-24")


@compilation.benchmark(name="wide-24")
def compile_wide(prepared_wide):
    compile_prepared(prepared_wide)


@system(scope="iteration")
def prepared_diamond():
    yield from prepared_build("diamond-depth-5")


@compilation.benchmark(name="diamond-depth-5")
def compile_diamond(prepared_diamond):
    compile_prepared(prepared_diamond)


@system(scope="iteration")
def prepared_generic():
    yield from prepared_build("generic-8-roots")


@compilation.benchmark(name="generic-8-roots")
def compile_generic(prepared_generic):
    compile_prepared(prepared_generic)


@system(scope="iteration")
def prepared_collection():
    yield from prepared_build("collection-12")


@compilation.benchmark(name="collection-12")
def compile_collection(prepared_collection):
    compile_prepared(prepared_collection)


@system(scope="iteration")
def prepared_template():
    yield from prepared_build("template-12")


@compilation.benchmark(name="template-12")
def compile_template(prepared_template):
    compile_prepared(prepared_template)


@system(scope="iteration")
def prepared_compatibility():
    yield from prepared_build("managed-warmup")


@compilation.benchmark(name="managed-warmup")
def compile_compatibility(prepared_compatibility):
    compile_prepared(prepared_compatibility)


related = Case(name="compiler-related-builds", tags=["compiler-optimization", "build"], min_iterations=3)


@related.benchmark(name="three-fresh-generics")
@related.parametrize("changed", [False, True], ids=["same-input", "changed-input"])
def related_generics(changed: bool):
    for index in range(3):
        with make_builder("generic-8-roots").build(**build_inputs("generic-8-roots", index if changed else 1)):
            pass


@system(scope="session")
def compiler_parent():
    builder = ContainerBuilder()
    builder.register(Leaf, lifespan="singleton")
    with builder.build() as parent:
        yield parent


overlays = Case(
    name="compiler-related-overlays",
    tags=["compiler-optimization", "build"],
    min_iterations=8,
    setup_timing="exclude",
    teardown_timing="exclude",
)


@overlays.benchmark(name="fresh-overlay")
@overlays.parametrize("changed", [False, True], ids=["inherited", "local-override"])
def related_overlays(compiler_parent, changed: bool):
    builder = compiler_parent.new_scope_builder()
    if changed:
        builder.register(Leaf, lifespan="scoped")
    builder.register(Worker)
    with builder.build():
        pass


def generic_matrix_builder():
    return make_builder("generic-8-roots")


MATRIX = BuildMatrix(
    [
        BuildVariant("production", generic_matrix_builder, build_args={"setting": 1}),
        BuildVariant("staging", generic_matrix_builder, build_args={"setting": 2}),
        BuildVariant("local", generic_matrix_builder, build_args={"setting": 3}),
    ],
    reference="production",
)
matrix_case = Case(name="compiler-matrix", tags=["compiler-optimization", "build", "matrix"], min_iterations=2)


@matrix_case.benchmark(name="three-variants-and-reports")
def matrix_check():
    report = MATRIX.check()
    if not report.is_valid:
        raise AssertionError("Compiler baseline matrix must be valid")
    return report
