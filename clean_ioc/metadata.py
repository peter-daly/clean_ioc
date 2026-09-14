"""Public metadata used during composition and graph inspection."""

from dataclasses import dataclass

__all__ = ["Tag"]


@dataclass(frozen=True, slots=True)
class Tag:
    name: str
    value: str | None = None

    def __iter__(self):
        yield self.name
        if self.value is not None:
            yield self.value
