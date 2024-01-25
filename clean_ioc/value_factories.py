from typing import Any
from . import _empty
from .functional_utils import constant

all_registrations = constant(True)


def use_default_value(default_value: Any, *_):
    """
    Returns the default value provided.

    Args:
        default_value (Any): The default value to be returned.
    Returns:
        Any: The default value.
    """
    return default_value


def set_value(value: Any):
    """
    Set the value of a variable.

    Args:
        value (Any): The value to be set.

    Returns:
        None
    """
    return constant(value)


dont_use_default_parameter = constant(_empty())
