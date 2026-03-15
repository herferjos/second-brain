"""Abstract interfaces for engine runtime contracts."""

import abc
from typing import Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMClient(abc.ABC):
    """Interface for text generation. Implementations call configured endpoints."""

    @abc.abstractmethod
    def generate(self, system: str, user: str, output_model: Type[T]) -> T:
        ...
