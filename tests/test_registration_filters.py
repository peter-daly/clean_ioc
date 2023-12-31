from clean_ioc.registration_filters import (
    has_tag,
    has_tag_with_value_or_missing_tag,
    has_tag_with_value_in,
)
from clean_ioc import Registration, Lifespan, Tag
from assertive import assert_that


def test_has_tag():
    registration = Registration(
        service_type=int,
        implementation=lambda: 5,
        lifespan=Lifespan.once_per_graph,
        tags=[Tag("name", "value")],
    )

    assert_that(has_tag("name")(registration)).matches(True)
    assert_that(has_tag("name", "value")(registration)).matches(True)
    assert_that(has_tag("name", "val")(registration)).matches(False)
    assert_that(has_tag("yourname")(registration)).matches(False)


def test_has_tag_with_value_or_missing_tag():
    registration = Registration(
        service_type=int,
        implementation=lambda: 5,
        lifespan=Lifespan.once_per_graph,
        tags=[Tag("name", "value")],
    )

    assert_that(
        has_tag_with_value_or_missing_tag("name", "value")(registration)
    ).matches(True)
    assert_that(has_tag_with_value_or_missing_tag("name", "val")(registration)).matches(
        False
    )
    assert_that(
        has_tag_with_value_or_missing_tag("yourname", "yourvalue")(registration)
    ).matches(True)


def test_has_tag_with_value_in():
    registration = Registration(
        service_type=int,
        implementation=lambda: 5,
        lifespan=Lifespan.once_per_graph,
        tags=[Tag("name", "value")],
    )

    assert_that(has_tag_with_value_in("name", "value", "value2")(registration)).matches(
        True
    )
    assert_that(has_tag_with_value_in("name", "val", "val2")(registration)).matches(
        False
    )
    assert_that(
        has_tag_with_value_in("yourname", "value", "val")(registration)
    ).matches(False)
