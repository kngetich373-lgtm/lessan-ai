"""Dependency Injection container for Lessan AI."""

import threading
from typing import Any, Callable, Dict, Generic, Optional, Type, TypeVar, cast

T = TypeVar("T")


class ServiceNotFoundError(KeyError):
    """Raised when a service is requested but not registered."""


class CircularDependencyError(RuntimeError):
    """Raised when a circular dependency is detected during resolution."""


class _ServiceRecord:
    """Internal record describing how to build a service."""

    def __init__(
        self,
        factory: Optional[Callable[..., Any]] = None,
        instance: Optional[Any] = None,
        singleton: bool = True,
    ):
        self.factory = factory
        self.instance = instance
        self.singleton = singleton


class Container:
    """A thread-safe dependency injection container.

    Supports:
      - Singleton and transient (non-singleton) registrations.
      - Registration from an existing instance.
      - Auto-resolution of constructor dependencies by type hint.
      - Factories that receive the container itself as an argument.
    """

    def __init__(self) -> None:
        self._records: Dict[str, _ServiceRecord] = {}
        self._lock = threading.RLock()
        self._resolving: set = set()

    # ------------------------------------------------------------------ #
    # Registration
    # ------------------------------------------------------------------ #
    def register(
        self,
        service_type: Type[T],
        factory: Optional[Callable[..., T]] = None,
        *,
        instance: Optional[T] = None,
        singleton: bool = True,
    ) -> "Container":
        """Register a service.

        Either ``factory`` or ``instance`` must be provided.

        Args:
            service_type: The interface/class to register.
            factory: A callable that builds the service. If the factory
                accepts a single argument it is invoked with the container;
                otherwise it is invoked with no arguments.
            instance: An already-constructed instance to reuse.
            singleton: If True (default), the same instance is returned on
                every resolution; otherwise a new one is built each time.
        """
        key = self._key_for(service_type)
        with self._lock:
            self._records[key] = _ServiceRecord(
                factory=factory,
                instance=instance,
                singleton=singleton,
            )
        return self

    def register_factory(
        self,
        service_type: Type[T],
        factory: Callable[[Any], T],
        *,
        singleton: bool = True,
    ) -> "Container":
        """Register a service using a factory callable."""
        return self.register(service_type, factory=factory, singleton=singleton)

    def register_instance(self, service_type: Type[T], instance: T) -> "Container":
        """Register an already-constructed instance as a singleton."""
        return self.register(service_type, instance=instance, singleton=True)

    def register_transient(self, service_type: Type[T], factory: Callable[..., T]) -> "Container":
        """Register a service that is rebuilt on every resolution."""
        return self.register(service_type, factory=factory, singleton=False)

    # ------------------------------------------------------------------ #
    # Resolution
    # ------------------------------------------------------------------ #
    def resolve(self, service_type: Type[T]) -> T:
        """Resolve a service to an instance."""
        key = self._key_for(service_type)
        with self._lock:
            record = self._records.get(key)
            if record is None:
                raise ServiceNotFoundError(
                    f"No service registered for {service_type.__name__} ({key})"
                )

            if record.singleton and record.instance is not None:
                return cast(T, record.instance)

            if key in self._resolving:
                raise CircularDependencyError(
                    f"Circular dependency detected while resolving: {key}"
                )

            self._resolving.add(key)
            try:
                instance: Any
                if record.instance is not None:
                    instance = record.instance
                elif record.factory is not None:
                    instance = record.factory(self)
                else:
                    instance = self._auto_construct(service_type)

                if record.singleton:
                    record.instance = instance
                return cast(T, instance)
            finally:
                self._resolving.discard(key)

    def try_resolve(self, service_type: Type[T]) -> Optional[T]:
        """Resolve a service, returning None if it is not registered."""
        try:
            return self.resolve(service_type)
        except ServiceNotFoundError:
            return None

    def has(self, service_type: Type[T]) -> bool:
        """Return True if a service is registered."""
        key = self._key_for(service_type)
        with self._lock:
            return key in self._records

    def remove(self, service_type: Type[T]) -> bool:
        """Unregister a service. Returns True if it existed."""
        key = self._key_for(service_type)
        with self._lock:
            return self._records.pop(key, None) is not None

    def clear(self) -> None:
        """Remove all registrations."""
        with self._lock:
            self._records.clear()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _auto_construct(self, service_type: Type[T]) -> T:
        """Build an instance by injecting constructor dependencies."""
        import inspect

        try:
            init = service_type.__init__
        except AttributeError:
            return service_type()

        sig = inspect.signature(init)
        params = [
            p
            for p in sig.parameters.values()
            if p.name not in ("self",) and p.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        ]

        kwargs: Dict[str, Any] = {}
        for param in params:
            annotation = param.annotation
            if annotation is inspect.Parameter.empty:
                if param.default is inspect.Parameter.empty:
                    raise ServiceNotFoundError(
                        f"Cannot auto-wire untyped parameter '{param.name}' "
                        f"for {service_type.__name__}"
                    )
                continue  # has a default — leave it
            try:
                kwargs[param.name] = self.resolve(annotation)
            except ServiceNotFoundError:
                if param.default is inspect.Parameter.empty:
                    raise
                # Optional dependency — keep default

        return service_type(**kwargs)

    @staticmethod
    def _key_for(service_type: Type[T]) -> str:
        if isinstance(service_type, str):
            return service_type
        return f"{service_type.__module__}.{service_type.__qualname__}"


# Global default container
container = Container()