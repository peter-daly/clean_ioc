import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import ClassVar
from uuid import uuid4

from clean_ioc import Container

logger = logging.getLogger(__name__)


class BaseBundle(ABC):
    @abstractmethod
    def apply(self, container: Container): ...

    def __call__(self, container: Container):
        self.apply(container=container)


class RunOnceBundle(BaseBundle):
    BUNDLE_RUN_HISTORY: ClassVar[dict[str, list[str]]] = defaultdict(list)

    @abstractmethod
    def apply(self, container: Container): ...

    @abstractmethod
    def get_bundle_identifier(self) -> str: ...

    def __call__(self, container: Container):
        bundle_identifier = self.get_bundle_identifier()
        bundle_containers = self.__class__.BUNDLE_RUN_HISTORY[bundle_identifier]
        container_id = container.id

        if container_id in bundle_containers:
            logger.debug("Bundle %s attempted to run more than once on container %s", bundle_identifier, container_id)
            return

        self.apply(container=container)
        bundle_containers.append(container_id)


class OnlyRunOncePerInstanceBundle(RunOnceBundle):
    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        instance._instance_id = str(uuid4())  # type: ignore
        return instance

    def get_bundle_identifier(self) -> str:
        module = self.__class__.__module__
        class_name = self.__class__.__name__
        return f"{module}.{class_name}-{self._instance_id}"  # type: ignore


class OnlyRunOncePerClassBundle(RunOnceBundle):
    def get_bundle_identifier(self) -> str:
        module = self.__class__.__module__
        class_name = self.__class__.__name__
        return f"{module}.{class_name}"
