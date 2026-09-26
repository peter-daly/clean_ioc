import copy
import pickle
from typing import assert_type

import pytest

from clean_ioc import (
    ComponentSelector,
    ContainerBuilder,
    DecoratorTemplate,
    ServiceGroup,
    Tag,
    Undefined,
    default_component_filter,
    select,
)
from clean_ioc import component_filters as cf
from clean_ioc.bundles import BaseBundle


def make_str() -> str:
    return "value"


def make_int() -> int:
    return 1


def pickle_roundtrip(value):
    return pickle.loads(pickle.dumps(value))  # noqa: S301 - round-trip locally generated test data


@pytest.mark.parametrize("clone", [copy.copy, copy.deepcopy, pickle_roundtrip])
def test_selector_preserves_undefined_defaults_when_copied(clone):
    selector = clone(ComponentSelector[str].default())

    assert selector.implementation_type is Undefined
    assert selector.name is Undefined
    assert selector.lifespan is Undefined
    assert selector.tags is Undefined
    assert selector.service_type is Undefined
    assert selector.predicate is Undefined
    assert selector.to_filter() is default_component_filter


def test_generic_selector_preserves_type_and_default_filter():
    selector = ComponentSelector[str]()
    default = ComponentSelector[str].default()

    assert_type(selector, ComponentSelector[str])
    assert_type(default, ComponentSelector[str])
    assert_type(ComponentSelector[str].all(), ComponentSelector[str])
    assert_type(ComponentSelector[str](predicate=cf.is_named), ComponentSelector[str])
    assert_type(ComponentSelector(service_type=str), ComponentSelector[str])
    assert_type(ComponentSelector(implementation_type=str), ComponentSelector[str])
    assert_type(ComponentSelector(service_type=list[str]), ComponentSelector[list[str]])
    assert selector == default
    assert selector.to_filter() is default_component_filter


@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        (ComponentSelector(), {None}),
        (ComponentSelector.default(), {None}),
        (ComponentSelector.all(), {"primary", "other", "", None}),
        (ComponentSelector[str](), {None}),
        (ComponentSelector[str](service_type=str), {"primary", "", None}),
        (
            ComponentSelector(
                implementation_type=Undefined,
                name=Undefined,
                lifespan=Undefined,
                tags=Undefined,
                service_type=Undefined,
                predicate=Undefined,
            ),
            {None},
        ),
        (ComponentSelector(tags=[]), {"primary", "other", "", None}),
        (ComponentSelector(predicate=cf.all_components), {"primary", "other", "", None}),
        (ComponentSelector(predicate=lambda _: False), set()),
        (ComponentSelector(predicate=lambda component: component.name == "primary"), {"primary"}),
        (ComponentSelector(predicate=cf.with_name("primary") | cf.with_name("other")), {"primary", "other"}),
        (ComponentSelector(predicate=~cf.is_named), {None}),
        (ComponentSelector(name=None, predicate=cf.all_components), {None}),
        (ComponentSelector(name=None, predicate=cf.is_named), set()),
        (ComponentSelector(tags=[Tag("env", "prod")], predicate=cf.implementation_type_is(str)), {"primary"}),
        (ComponentSelector(tags=[Tag("env", "dev")], predicate=cf.implementation_type_is(int)), set()),
        (ComponentSelector(name=None), {None}),
        (ComponentSelector(service_type=None), set()),
        (ComponentSelector(implementation_type=None), set()),
        (ComponentSelector(implementation_type=str), {"primary", "", None}),
        (ComponentSelector(service_type=str), {"primary", "", None}),
        (ComponentSelector(service_type=int, implementation_type=str), set()),
        (ComponentSelector(name=""), {""}),
        (ComponentSelector(name="primary"), {"primary"}),
        (ComponentSelector(lifespan="singleton"), {"primary", "other"}),
        (ComponentSelector(tags=[Tag("env", "prod"), Tag("enabled")]), {"primary"}),
        (ComponentSelector(tags=[Tag("env")]), {"primary", "other", ""}),
        (ComponentSelector(tags=[Tag("missing")]), set()),
        (
            ComponentSelector(
                service_type=str,
                implementation_type=str,
                name="primary",
                lifespan="singleton",
                tags=[Tag("env", "prod"), Tag("enabled")],
                predicate=cf.is_named,
            ),
            {"primary"},
        ),
        (ComponentSelector(name="other", implementation_type=str), set()),
        (ComponentSelector(name="primary", lifespan="transient"), set()),
        (ComponentSelector(name="primary", tags=[Tag("env", "dev")]), set()),
    ],
)
def test_selector_matches_component_metadata(selector, expected):
    builder = ContainerBuilder()
    builder.register(
        str,
        factory=make_str,
        name="primary",
        lifespan="singleton",
        tags=[Tag("env", "prod"), Tag("enabled", "yes"), Tag("extra")],
    )
    builder.register(int, factory=make_int, name="other", lifespan="singleton", tags=[Tag("env", "prod")])
    builder.register(str, factory=make_str, name="", lifespan="transient", tags=[Tag("env", "dev")])
    builder.register(str, factory=make_str, lifespan="transient")
    components = [root.component for root in builder.build().graph.roots]

    assert {component.name for component in components if selector.to_filter()(component)} == expected


def test_selector_distinguishes_service_type_from_implementation_type():
    class Service:
        pass

    class Implementation(Service):
        pass

    builder = ContainerBuilder()
    builder.register(Service, Implementation)
    builder.register(Implementation)
    components = [root.component for root in builder.build().graph.roots]
    selector = ComponentSelector[Service](service_type=Service, implementation_type=Implementation)
    filter = selector.to_filter()

    assert [component.service_type for component in components if filter(component)] == [Service]


def test_selector_snapshots_tags_and_returns_composable_filters():
    tags = [Tag("enabled")]
    selector = ComponentSelector(tags=tags)
    from_iterator = ComponentSelector(tags=iter(tags))
    tags.clear()
    builder = ContainerBuilder()
    builder.register(str, factory=make_str, name="named", tags=[Tag("enabled")])
    builder.register(str, factory=make_str, tags=[Tag("enabled")])
    builder.register(int, factory=make_int)
    components = [root.component for root in builder.build().graph.roots]

    for value in (selector, from_iterator):
        for _ in range(2):
            filter = value.to_filter() & cf.is_not_named
            assert [component.service_type for component in components if filter(component)] == [str]


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        (ComponentSelector(implementation_type=str, tags=[Tag("env", "prod")]), "production"),
        (ComponentSelector.default(), "development"),
        (ComponentSelector(name=None), "development"),
        (ComponentSelector(name=Undefined), "development"),
        (ComponentSelector(tags=[]), "production"),
        (ComponentSelector.all(), "production"),
        (ComponentSelector(predicate=cf.with_name("api")), "production"),
    ],
)
def test_bundle_can_use_selector_for_dependency_selection_with_a_factory(endpoint, expected):
    class Service:
        def __init__(self, endpoint: str):
            self.endpoint = endpoint

    class ServiceBundle(BaseBundle):
        def __init__(self, endpoint: ComponentSelector[str] = ComponentSelector[str].default()):
            self.endpoint = endpoint

        def apply(self, builder):
            builder.register(Service, arguments={"endpoint": select(self.endpoint.to_filter())})

    def endpoint_factory() -> str:
        return "production"

    builder = ContainerBuilder()
    builder.register(str, instance="development")
    builder.register(str, factory=endpoint_factory, name="api", tags=[Tag("env", "prod")])
    builder.apply_bundle(ServiceBundle(endpoint))

    assert builder.build().resolve(Service).endpoint == expected


@pytest.mark.parametrize("invalid", [None, False, "named"])
def test_selector_rejects_non_callable_predicates(invalid):
    with pytest.raises(TypeError, match="ComponentSelector.predicate must be a component filter"):
        ComponentSelector(predicate=invalid)


def test_predicate_runs_only_when_filtering_components_that_match_metadata():
    calls = []

    def matches(component):
        calls.append(component.name)
        return True

    selector = ComponentSelector[str](name="selected", predicate=matches)
    filter = selector.to_filter()
    assert calls == []

    builder = ContainerBuilder()
    builder.register(str, instance="yes", name="selected")
    builder.register(str, instance="no", name="other")
    container = builder.build()

    assert container.resolve(str, filter=filter) == "yes"
    assert calls == ["selected"]


def test_selectors_distinguish_different_callable_policies():
    def named(name):
        return lambda component: component.name == name

    first = named("first")
    second = named("second")

    assert ComponentSelector(predicate=first) == ComponentSelector(predicate=first)
    assert ComponentSelector(predicate=first) != ComponentSelector(predicate=second)
    assert ComponentSelector.default() != ComponentSelector.all()


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        (None, {"uses-resource"}),
        (ComponentSelector.all(), {"uses-resource", "own-tag", "sessionless"}),
        (ComponentSelector(predicate=lambda _: False), set()),
    ],
)
def test_selector_carries_descendant_policy_through_decorator_templates(override, expected):
    class Transaction:
        pass

    class Resource:
        pass

    class Repository:
        def __init__(self, resource: Resource):
            self.resource = resource

    class Handler:
        disabled = False

    class ResourceHandler(Handler):
        def __init__(self, repository: Repository):
            self.repository = repository

    class DisabledHandler(ResourceHandler):
        disabled = True

    class TransactionalHandler(Handler):
        def __init__(self, inner: Handler, transaction: Transaction):
            self.inner = inner
            self.transaction = transaction

    builder = ContainerBuilder()
    handlers = ServiceGroup("handlers", service_type=Handler)
    transaction = Transaction()
    builder.register(Transaction, instance=transaction, name="main")
    builder.register(Transaction, name="unrelated")
    builder.register(Resource, tags=[Tag("transaction", "main")])
    builder.register(Repository)
    builder.register(Handler, ResourceHandler, name="uses-resource", groups=[handlers])
    builder.register(Handler, DisabledHandler, name="disabled", groups=[handlers])
    builder.register(Handler, name="own-tag", tags=[Tag("transaction", "main")], groups=[handlers])
    builder.register(Handler, name="sessionless", groups=[handlers])

    def template(source):
        applicability = (
            cf.has_descendant(cf.has_tag("transaction", source.name)) if override is None else override.to_filter()
        )
        selector = ComponentSelector[Handler](
            predicate=cf.implementation_matches_type_filter(
                lambda implementation: not getattr(implementation, "disabled", False)
            )
            & applicability
        )
        return DecoratorTemplate(
            services=handlers,
            decorator_type=TransactionalHandler,
            decorated_arg="inner",
            arguments={"transaction": select(cf.with_id(source.id))},
            when=selector.to_filter(),
        )

    builder.register_decorator_template(for_each=Transaction, template=template)
    container = builder.build()
    for name in ("uses-resource", "disabled", "own-tag", "sessionless"):
        handler = container.resolve(Handler, filter=cf.with_name(name))
        assert isinstance(handler, TransactionalHandler) == (name in expected)
        if override is None and isinstance(handler, TransactionalHandler):
            assert handler.transaction is transaction
            assert isinstance(handler.inner, ResourceHandler)
