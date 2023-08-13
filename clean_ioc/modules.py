from typing import ClassVar
from clean_ioc import Container
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class BaseModule(ABC):
    CLASS_RUN_ONCE: ClassVar[bool] = False
    INSTANCE_RUN_ONCE: ClassVar[bool] = True
    CLASS_HAS_RUN: ClassVar[bool] = False

    def __init__(self):
        self.instance_has_run = False

    @abstractmethod
    def run(self, container: Container):
        ...

    def __call__(self, container: Container):
        if self.INSTANCE_RUN_ONCE and self.instance_has_run:
            logging.warning("Module instance %s attempted to run more than once", self)
            return

        if self.CLASS_RUN_ONCE and self.CLASS_HAS_RUN:
            logging.warning(
                "Module class %s attempted to run more than once", self.__class__
            )
            return

        self.run(container=container)
        self.instance_has_run = True
        self.__class__.CLASS_HAS_RUN = True
