import inspect

import clean_ioc.registration_filters as registration_filters
from clean_ioc.core import FactoryActivator, Lifespan, Tag, _Registration
from clean_ioc.registration_filters import (
    has_tag,
    has_tag_with_value_in,
    has_tag_with_value_or_missing_tag,
    with_id,
)


def test_all_public_registration_filters_have_docstrings():
    for name in registration_filters.__all__:
        assert inspect.getdoc(getattr(registration_filters, name))


def test_with_id():
    registration = _Registration(
        service_type=int,
        implementation=lambda: 5,
        lifespan=Lifespan.once_per_graph,
        activator_class=FactoryActivator,
    )

    assert with_id(registration.id)(registration) is True
    assert with_id("another-registration-id")(registration) is False


def test_has_tag():
    registration = _Registration(
        service_type=int,
        implementation=lambda: 5,
        lifespan=Lifespan.once_per_graph,
        tags=[Tag("name", "value")],
        activator_class=FactoryActivator,
    )

    assert has_tag("name")(registration) is True
    assert has_tag("name", "value")(registration) is True
    assert has_tag("name", "val")(registration) is False
    assert has_tag("yourname")(registration) is False


def test_has_tag_with_value_or_missing_tag():
    registration = _Registration(
        service_type=int,
        implementation=lambda: 5,
        lifespan=Lifespan.once_per_graph,
        tags=[Tag("name", "value")],
        activator_class=FactoryActivator,
    )

    assert has_tag_with_value_or_missing_tag("name", "value")(registration) is True
    assert has_tag_with_value_or_missing_tag("name", "val")(registration) is False
    assert has_tag_with_value_or_missing_tag("yourname", "yourvalue")(registration) is True


def test_has_tag_with_value_in():
    registration = _Registration(
        service_type=int,
        implementation=lambda: 5,
        lifespan=Lifespan.once_per_graph,
        tags=[Tag("name", "value")],
        activator_class=FactoryActivator,
    )

    assert has_tag_with_value_in("name", "value", "value2")(registration) is True
    assert has_tag_with_value_in("name", "val", "val2")(registration) is False
    assert has_tag_with_value_in("yourname", "value", "val")(registration) is False


def test_tags_can_be_destructured_into_the_filter():
    tag = Tag("name", "value")
    registration = _Registration(
        service_type=int,
        implementation=lambda: 5,
        lifespan=Lifespan.once_per_graph,
        tags=[tag],
        activator_class=FactoryActivator,
    )

    assert has_tag(*tag)(registration) is True


def test_name_only_tags_can_be_destructured_into_the_filter():
    tag = Tag("name")
    registration = _Registration(
        service_type=int,
        implementation=lambda: 5,
        lifespan=Lifespan.once_per_graph,
        tags=[tag],
        activator_class=FactoryActivator,
    )

    assert has_tag(*tag)(registration) is True
