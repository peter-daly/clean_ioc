from clean_ioc.type_filters import named


def test_has_name():
    x = named("int")

    assert x(int)
