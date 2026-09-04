from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

T = TypeVar("T")


class ServiceStatus(StrEnum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"


@dataclass
class ServiceResponse(Generic[T]):
    status: ServiceStatus
    data: T | None = None
