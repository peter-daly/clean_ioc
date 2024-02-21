import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import ClassVar

from clean_ioc import Container

logger = logging.getLogger(__name__)


class BaseBundle(ABC):
    @abstractmethod
    def apply(self, container: Container):
        ...

    def __call__(self, container: Container):
        self.apply(container=container)


class OnlyRunOncePerInstanceBundle(BaseBundle):
    containers_where_instance_has_run: list[int]

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        instance.containers_where_instance_has_run = []
        return instance

    def bundle_has_run_in_container(self, container: Container):
        return id(container) in self.containers_where_instance_has_run

    def mark_bundle_as_ran_in_container(self, container: Container):
        self.containers_where_instance_has_run.append(id(container))

    @abstractmethod
    def apply(self, container: Container):
        ...

    def __call__(self, container: Container):
        if self.bundle_has_run_in_container(container):
            logging.warning("Module instance %s attempted to run more than once", self)
            return

        self.apply(container=container)
        self.mark_bundle_as_ran_in_container(container)


class OnlyRunOncePerClassBundle(BaseBundle):
    CONTAINERS_WHERE_CLASS_HAS_RUN: ClassVar[dict[type, list[int]]] = defaultdict(list)

    @classmethod
    def bundle_has_run_in_container(cls, container: Container):
        return id(container) in cls.CONTAINERS_WHERE_CLASS_HAS_RUN[cls]

    @classmethod
    def mark_bundle_as_ran_in_container(cls, container: Container):
        cls.CONTAINERS_WHERE_CLASS_HAS_RUN[cls].append(id(container))

    @abstractmethod
    def apply(self, container: Container):
        ...

    def __call__(self, container: Container):
        if self.__class__.bundle_has_run_in_container(container):
            logging.warning(
                "Module class %s attempted to run more than once", type(self)
            )
            return

        self.apply(container=container)
        self.__class__.mark_bundle_as_ran_in_container(container)
