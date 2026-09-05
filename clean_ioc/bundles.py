import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import ClassVar
from uuid import uuid4

from clean_ioc import ComponentBuilder

logger = logging.getLogger(__name__)


class BaseBundle(ABC):
    @abstractmethod
    def apply(self, builder: ComponentBuilder): ...

    def __call__(self, builder: ComponentBuilder):
        self.apply(builder)


class RunOnceBundle(BaseBundle):
    BUNDLE_RUN_HISTORY: ClassVar[dict[str, list[str]]] = defaultdict(list)

    @abstractmethod
    def apply(self, builder: ComponentBuilder): ...

    @abstractmethod
    def get_bundle_identifier(self) -> str: ...

    def __call__(self, builder: ComponentBuilder):
        bundle_identifier = self.get_bundle_identifier()
        bundle_containers = self.__class__.BUNDLE_RUN_HISTORY[bundle_identifier]
        builder_id = builder.id

        if builder_id in bundle_containers:
            logger.debug("Bundle %s attempted to run more than once on builder %s", bundle_identifier, builder_id)
            return

        self.apply(builder)
        bundle_containers.append(builder_id)


class OnlyRunOncePerInstanceBundle(RunOnceBundle):
    _instance_id: str

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        instance._instance_id = str(uuid4())
        return instance

    def get_bundle_identifier(self) -> str:
        module = self.__class__.__module__
        class_name = self.__class__.__name__
        return f"{module}.{class_name}-{self._instance_id}"


class OnlyRunOncePerClassBundle(RunOnceBundle):
    def get_bundle_identifier(self) -> str:
        module = self.__class__.__module__
        class_name = self.__class__.__name__
        return f"{module}.{class_name}"
