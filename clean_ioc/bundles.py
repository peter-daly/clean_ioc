from typing import ClassVar
from clean_ioc import Container
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class BaseBundle(ABC):
    @abstractmethod
    def apply(self, container: Container):
        ...

    def __call__(self, container: Container):
        self.apply(container=container)


class OnlyRunOncePerInstanceBundle(BaseBundle):
    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        instance.instance_has_run = False
        return instance

    @abstractmethod
    def apply(self, container: Container):
        ...

    def __call__(self, container: Container):
        if self.instance_has_run:
            logging.warning("Module instance %s attempted to run more than once", self)
            return

        self.apply(container=container)
        self.instance_has_run = True


class OnlyRunOncePerClassBundle(BaseBundle):
    CLASS_HAS_RUN: ClassVar[bool] = False

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        cls.class_has_run = False
        return instance

    @abstractmethod
    def apply(self, container: Container):
        ...

    def __call__(self, container: Container):
        if self.__class__.CLASS_HAS_RUN:
            logging.warning(
                "Module class %s attempted to run more than once", type(self)
            )
            return

        self.apply(container=container)
        self.__class__.CLASS_HAS_RUN = True
