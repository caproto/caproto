from __future__ import annotations

import abc
import typing
from typing import Any, Optional, Protocol, Type, TypeVar

if typing.TYPE_CHECKING:
    from .server import PVGroup


T_contra = TypeVar("T_contra", contravariant=True)


class _AsyncEvent(Protocol):
    """Async Event API supported by the caproto server."""

    def set(self) -> None:
        """Set the event."""
        ...

    def is_set(self) -> bool:
        """Is the event set?"""
        ...

    async def wait(self, timeout: Optional[float] = None) -> None:
        """Wait ``timeout`` for the event to be set."""
        ...


class _AsyncLibrary(Protocol):
    """Async library layer API supported by the caproto server."""

    async def sleep(self, seconds: float) -> None:
        """Sleep for ``seconds`` seconds."""
        ...


class _AsyncQueue(Protocol):
    """Async queue API supported by the caproto server."""

    async def async_get(self) -> Any:
        ...

    async def async_put(self, value: Any) -> None:
        ...

    def get(self) -> Any:
        ...

    def put(self, value: Any) -> None:
        ...


class AsyncLibraryLayer(abc.ABC):
    """
    Library compatibility layer.

    To be subclassed/customized by async library layer for compatibility Then,
    a single IOC written within the high-level server framework can potentially
    use the same code base and still be run on either curio or trio, etc.
    """

    name: str
    Event: Type[_AsyncEvent]
    ThreadsafeQueue: Type[_AsyncQueue]
    library: _AsyncLibrary

    async def sleep(self, seconds: float) -> None:
        """Sleep for ``seconds`` seconds."""
        raise NotImplementedError()


class Getter(Protocol[T_contra]):
    """Getter method for a pvproperty."""

    async def __call__(_self, self: PVGroup, instance: T_contra) -> Optional[Any]:
        ...


class Putter(Protocol[T_contra]):
    """Putter method for a pvproperty."""

    async def __call__(
        _self, self: PVGroup, instance: T_contra, value: Any
    ) -> Optional[Any]:
        ...


class Startup(Protocol[T_contra]):
    """Startup method for a pvproperty."""

    async def __call__(
        _self, self: PVGroup, instance: T_contra, async_lib: AsyncLibraryLayer
    ) -> None:
        ...


class Scan(Protocol[T_contra]):
    """Scan method for a pvproperty."""

    async def __call__(
        _self, self: PVGroup, instance: T_contra, async_lib: AsyncLibraryLayer
    ) -> None:
        ...


class Shutdown(Protocol[T_contra]):
    """Shutdown method for a pvproperty."""

    async def __call__(
        _self, self: PVGroup, instance: T_contra, async_lib: AsyncLibraryLayer
    ) -> None:
        ...


class BoundGetter(Protocol[T_contra]):
    """Getter method bound to a PVGroup."""

    async def __call__(_self, instance: T_contra) -> Optional[Any]:
        ...


class BoundPutter(Protocol[T_contra]):
    """Putter method bound to a PVGroup."""

    async def __call__(_self, instance: T_contra, value: Any) -> Optional[Any]:
        ...


class BoundStartup(Protocol[T_contra]):
    """Startup method bound to a PVGroup."""

    async def __call__(_self, instance: T_contra, async_lib: AsyncLibraryLayer) -> None:
        ...


class BoundScan(Protocol[T_contra]):
    """Scan method bound to a PVGroup."""

    async def __call__(_self, instance: T_contra, async_lib: AsyncLibraryLayer) -> None:
        ...


class BoundShutdown(Protocol[T_contra]):
    """Shutdown method bound to a PVGroup."""

    async def __call__(_self, instance: T_contra, async_lib: AsyncLibraryLayer) -> None:
        ...


class AinitHook(Protocol):
    """Async __ainit__ method for running a server."""

    async def __call__(self, async_lib: AsyncLibraryLayer) -> None:
        ...
