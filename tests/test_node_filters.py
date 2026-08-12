import inspect

import clean_ioc.node_filters as node_filters


def test_all_public_node_filters_have_docstrings():
    for name in node_filters.__all__:
        assert inspect.getdoc(getattr(node_filters, name))
