from assertive import assert_that

from clean_ioc.core import FactoryActivator, Lifespan, Tag, _Registration
from clean_ioc.registration_filters import (
    has_tag,
    has_tag_with_value_in,
    has_tag_with_value_or_missing_tag,
)


def test_has_tag():
    registration = _Registration(
        service_type=int,
        implementation=lambda: 5,
        lifespan=Lifespan.once_per_graph,
        tags=[Tag("name", "value")],
        activator_class=FactoryActivator,
    )

    assert_that(has_tag("name")(registration)).matches(True)
    assert_that(has_tag("name", "value")(registration)).matches(True)
    assert_that(has_tag("name", "val")(registration)).matches(False)
    assert_that(has_tag("yourname")(registration)).matches(False)


def test_has_tag_with_value_or_missing_tag():
    registration = _Registration(
        service_type=int,
        implementation=lambda: 5,
        lifespan=Lifespan.once_per_graph,
        tags=[Tag("name", "value")],
        activator_class=FactoryActivator,
    )

    assert_that(has_tag_with_value_or_missing_tag("name", "value")(registration)).matches(True)
    assert_that(has_tag_with_value_or_missing_tag("name", "val")(registration)).matches(False)
    assert_that(has_tag_with_value_or_missing_tag("yourname", "yourvalue")(registration)).matches(True)


def test_has_tag_with_value_in():
    registration = _Registration(
        service_type=int,
        implementation=lambda: 5,
        lifespan=Lifespan.once_per_graph,
        tags=[Tag("name", "value")],
        activator_class=FactoryActivator,
    )

    assert_that(has_tag_with_value_in("name", "value", "value2")(registration)).matches(True)
    assert_that(has_tag_with_value_in("name", "val", "val2")(registration)).matches(False)
    assert_that(has_tag_with_value_in("yourname", "value", "val")(registration)).matches(False)


def test_tags_can_be_destructured_into_the_filter():
    tag = Tag("name", "value")
    registration = _Registration(
        service_type=int,
        implementation=lambda: 5,
        lifespan=Lifespan.once_per_graph,
        tags=[tag],
        activator_class=FactoryActivator,
    )

    assert_that(has_tag(*tag)(registration)).matches(True)


def test_name_only_tags_can_be_destructured_into_the_filter():
    tag = Tag("name")
    registration = _Registration(
        service_type=int,
        implementation=lambda: 5,
        lifespan=Lifespan.once_per_graph,
        tags=[tag],
        activator_class=FactoryActivator,
    )

    assert_that(has_tag(*tag)(registration)).matches(True)
