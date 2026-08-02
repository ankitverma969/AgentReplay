"""Memory cache and object pooling utilities for large traces."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from threading import RLock
from typing import Generic, TypeVar

KeyT = TypeVar("KeyT")
ValueT = TypeVar("ValueT")


class LRUCache(Generic[KeyT, ValueT]):
    """Small thread-safe least-recently-used cache for trace windows and indexes."""

    def __init__(self, max_size: int = 128) -> None:
        """Create an LRU cache."""
        if max_size <= 0:
            msg = "LRU cache max_size must be greater than zero."
            raise ValueError(msg)
        self._max_size = max_size
        self._values: OrderedDict[KeyT, ValueT] = OrderedDict()
        self._lock = RLock()

    def get(self, key: KeyT) -> ValueT | None:
        """Return a cached value and mark it as recently used."""
        with self._lock:
            if key not in self._values:
                return None
            value = self._values.pop(key)
            self._values[key] = value
            return value

    def put(self, key: KeyT, value: ValueT) -> None:
        """Store a value and evict the least recently used item when necessary."""
        with self._lock:
            if key in self._values:
                self._values.pop(key)
            self._values[key] = value
            while len(self._values) > self._max_size:
                self._values.popitem(last=False)

    def clear(self) -> None:
        """Remove all cached entries."""
        with self._lock:
            self._values.clear()

    def __len__(self) -> int:
        """Return the number of cached entries."""
        with self._lock:
            return len(self._values)


class ObjectPool(Generic[ValueT]):
    """Thread-safe bounded object pool for reusable buffers and builders."""

    def __init__(self, factory: Callable[[], ValueT], *, max_size: int = 64) -> None:
        """Create an object pool."""
        if max_size <= 0:
            msg = "Object pool max_size must be greater than zero."
            raise ValueError(msg)
        self._factory = factory
        self._max_size = max_size
        self._items: list[ValueT] = []
        self._lock = RLock()

    def acquire(self) -> ValueT:
        """Acquire a pooled object or create a new one."""
        with self._lock:
            if self._items:
                return self._items.pop()
        return self._factory()

    def release(self, item: ValueT) -> None:
        """Return an object to the pool if there is capacity."""
        with self._lock:
            if len(self._items) < self._max_size:
                self._items.append(item)

    def clear(self) -> None:
        """Remove all pooled objects."""
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        """Return the number of currently pooled objects."""
        with self._lock:
            return len(self._items)


__all__ = ["LRUCache", "ObjectPool"]
