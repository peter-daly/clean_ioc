import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import ClassVar
from uuid import uuid4

from clean_ioc.components import BundleRunScope, ComponentBuilder

logger = logging.getLogger(__name__)


class BaseBundle(ABC):
    @abstractmethod
    def apply(self, builder: ComponentBuilder): ...

    def __call__(self, builder: ComponentBuilder):
        self.apply(builder)


class RunOnceBundle(BaseBundle):
    BUNDLE_RUN_HISTORY: ClassVar[dict[str, set[tuple[BundleRunScope, str]]]] = defaultdict(set)
    run_once_per: ClassVar[BundleRunScope] = "boundary"

    @abstractmethod
    def apply(self, builder: ComponentBuilder): ...

    @abstractmethod
    def get_bundle_identifier(self) -> str: ...

    def __call__(self, builder: ComponentBuilder):
        bundle_identifier = self.get_bundle_identifier()
        bundle_containers = self.__class__.BUNDLE_RUN_HISTORY[bundle_identifier]
        builder_id = builder.id if self.run_once_per == "boundary" else builder.bundle_run_key(self.run_once_per)
        run_key = (self.run_once_per, builder_id)

        if run_key in bundle_containers:
            logger.debug(
                "Bundle %s attempted to run more than once in %s %s",
                bundle_identifier,
                self.run_once_per,
                builder_id,
            )
            return

        self.apply(builder)
        bundle_containers.add(run_key)


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
