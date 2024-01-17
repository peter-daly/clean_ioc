from typing import ClassVar
from clean_ioc import Container
from abc import ABC, abstractmethod
import logging

from clean_ioc.utils import deprecated, send_deprecation_warning

logger = logging.getLogger(__name__)


send_deprecation_warning("clean_ioc.modules should be replaced by clean_ioc.bundles")


@deprecated("Use BaseBundle instead")
class BaseModule(ABC):
    CLASS_RUN_ONCE: ClassVar[bool] = False
    INSTANCE_RUN_ONCE: ClassVar[bool] = True
    CLASS_HAS_RUN: ClassVar[bool] = False

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        instance.instance_has_run = False
        return instance

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
