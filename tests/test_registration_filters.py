from clean_ioc.registration_filters import (
    has_tag,
    has_tag_with_value_or_missing_tag,
    has_tag_with_value_in,
)
from clean_ioc import Registration, Lifespan, Tag
from expects import expect, be_true, be_false


def test_has_tag():
    registration = Registration(
        service_type=int,
        implementation=lambda: 5,
        lifespan=Lifespan.once_per_graph,
        tags=[Tag("name", "value")],
    )

    expect(has_tag("name")(registration)).to(be_true)
    expect(has_tag("name", "value")(registration)).to(be_true)
    expect(has_tag("name", "val")(registration)).to(be_false)
    expect(has_tag("yourname")(registration)).to(be_false)


def test_has_tag_with_value_or_missing_tag():
    registration = Registration(
        service_type=int,
        implementation=lambda: 5,
        lifespan=Lifespan.once_per_graph,
        tags=[Tag("name", "value")],
    )

    expect(has_tag_with_value_or_missing_tag("name", "value")(registration)).to(be_true)
    expect(has_tag_with_value_or_missing_tag("name", "val")(registration)).to(be_false)
    expect(has_tag_with_value_or_missing_tag("yourname", "yourvalue")(registration)).to(
        be_true
    )


def test_has_tag_with_value_in():
    registration = Registration(
        service_type=int,
        implementation=lambda: 5,
        lifespan=Lifespan.once_per_graph,
        tags=[Tag("name", "value")],
    )

    expect(has_tag_with_value_in("name", "value", "value2")(registration)).to(be_true)
    expect(has_tag_with_value_in("name", "val", "val2")(registration)).to(be_false)
    expect(has_tag_with_value_in("yourname", "value", "val")(registration)).to(be_false)
