from typing import Any, Callable

from theutilitybelt.functional.utils import constant

from .core import Registration

all_items = constant(True)


def depulication_checker(getter: Callable[[Registration], Any]):
    def checker(acc: list[Registration], registration: Registration) -> bool:
        current_items = [getter(r) for r in acc]
        return getter(registration) not in current_items

    return checker


implementation_does_not_already_exist = depulication_checker(lambda r: r.implementation)
name_does_not_already_exist = depulication_checker(lambda r: r.name)
