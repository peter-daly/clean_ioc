import pytest

from clean_ioc import ComponentSelector, ContainerBuilder, Tag, select
from clean_ioc import component_filters as cf
from clean_ioc.bundles import BaseBundle


def make_str() -> str:
    return "value"


def make_int() -> int:
    return 1


@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        (ComponentSelector(), {"primary", "other", "", None}),
        (
            ComponentSelector(implementation_type=None, name=None, lifespan=None, tags=None, service_type=None),
            {"primary", "other", "", None},
        ),
        (ComponentSelector(tags=[]), {"primary", "other", "", None}),
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
    filter = ComponentSelector(service_type=Service, implementation_type=Implementation).to_filter()

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


def test_bundle_can_use_selector_for_dependency_selection_with_a_factory():
    class Service:
        def __init__(self, endpoint: str):
            self.endpoint = endpoint

    class ServiceBundle(BaseBundle):
        def __init__(self, endpoint: ComponentSelector):
            self.endpoint = endpoint

        def apply(self, builder):
            builder.register(Service, arguments={"endpoint": select(self.endpoint.to_filter())})

    def endpoint_factory() -> str:
        return "production"

    builder = ContainerBuilder()
    builder.register(str, instance="development")
    builder.register(str, factory=endpoint_factory, name="api", tags=[Tag("env", "prod")])
    builder.apply_bundle(ServiceBundle(ComponentSelector(implementation_type=str, tags=[Tag("env", "prod")])))

    assert builder.build().resolve(Service).endpoint == "production"
