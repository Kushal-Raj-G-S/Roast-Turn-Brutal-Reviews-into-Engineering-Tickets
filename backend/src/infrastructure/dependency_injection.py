"""
Dependency Injection Container
Manages service lifecycle and dependencies using the Service Locator pattern.
"""

from typing import Dict, Type, Any, Optional, Callable
import inspect
from functools import lru_cache


class ServiceLifetime:
    """Service lifetime scopes."""
    SINGLETON = "singleton"  # One instance for app lifetime
    SCOPED = "scoped"  # One instance per request/transaction
    TRANSIENT = "transient"  # New instance every time


class DependencyContainer:
    """
    Lightweight IoC container for dependency injection.
    
    Features:
    - Service registration with lifetime management
    - Auto constructor injection
    - Factory functions
    - Singleton/Scoped/Transient lifetimes
    
    Example:
        container = DependencyContainer()
        container.register(IEmbeddingProvider, SentenceTransformerProvider, ServiceLifetime.SINGLETON)
        provider = container.resolve(IEmbeddingProvider)
    """

    def __init__(self):
        self._services: Dict[Type, Dict[str, Any]] = {}
        self._singletons: Dict[Type, Any] = {}
        self._scoped_instances: Dict[Type, Any] = {}

    def register(
        self,
        interface: Type,
        implementation: Optional[Type] = None,
        lifetime: str = ServiceLifetime.TRANSIENT,
        factory: Optional[Callable] = None,
        instance: Optional[Any] = None
    ):
        """
        Register a service.
        
        Args:
            interface: Interface/abstract class
            implementation: Concrete implementation class
            lifetime: Service lifetime (singleton/scoped/transient)
            factory: Optional factory function
            instance: Optional pre-created instance (implies singleton)
        """
        if instance is not None:
            # Register pre-created instance as singleton
            self._singletons[interface] = instance
            self._services[interface] = {
                "lifetime": ServiceLifetime.SINGLETON,
                "instance": instance
            }
        elif factory is not None:
            # Register factory function
            self._services[interface] = {
                "lifetime": lifetime,
                "factory": factory
            }
        elif implementation is not None:
            # Register implementation class
            self._services[interface] = {
                "lifetime": lifetime,
                "implementation": implementation
            }
        else:
            raise ValueError("Must provide implementation, factory, or instance")

    def register_singleton(
        self,
        interface: Type,
        implementation: Optional[Type] = None,
        factory: Optional[Callable] = None,
        instance: Optional[Any] = None
    ):
        """Register a singleton service."""
        self.register(interface, implementation, ServiceLifetime.SINGLETON, factory, instance)

    def register_scoped(
        self,
        interface: Type,
        implementation: Type
    ):
        """Register a scoped service."""
        self.register(interface, implementation, ServiceLifetime.SCOPED)

    def register_transient(
        self,
        interface: Type,
        implementation: Type
    ):
        """Register a transient service."""
        self.register(interface, implementation, ServiceLifetime.TRANSIENT)

    def resolve(self, interface: Type) -> Any:
        """
        Resolve a service instance.
        
        Args:
            interface: Interface/abstract class to resolve
        
        Returns:
            Service instance
        """
        if interface not in self._services:
            raise ValueError(f"Service {interface} not registered")

        service_config = self._services[interface]
        lifetime = service_config["lifetime"]

        # Handle singleton
        if lifetime == ServiceLifetime.SINGLETON:
            if interface in self._singletons:
                return self._singletons[interface]
            
            # Create singleton instance
            instance = self._create_instance(service_config)
            self._singletons[interface] = instance
            return instance

        # Handle scoped
        if lifetime == ServiceLifetime.SCOPED:
            if interface in self._scoped_instances:
                return self._scoped_instances[interface]
            
            # Create scoped instance
            instance = self._create_instance(service_config)
            self._scoped_instances[interface] = instance
            return instance

        # Handle transient (always create new)
        return self._create_instance(service_config)

    def _create_instance(self, service_config: Dict[str, Any]) -> Any:
        """Create service instance from configuration."""
        # Use factory if provided
        if "factory" in service_config:
            factory = service_config["factory"]
            return factory(self)

        # Use pre-created instance
        if "instance" in service_config:
            return service_config["instance"]

        # Create from implementation class
        implementation = service_config["implementation"]
        return self._instantiate_with_injection(implementation)

    def _instantiate_with_injection(self, cls: Type) -> Any:
        """
        Instantiate class with constructor dependency injection.
        """
        # Get constructor signature
        sig = inspect.signature(cls.__init__)
        params = sig.parameters

        # Resolve dependencies
        kwargs = {}
        for param_name, param in params.items():
            if param_name == "self":
                continue
            
            # Try to resolve by type annotation
            if param.annotation != inspect.Parameter.empty:
                try:
                    kwargs[param_name] = self.resolve(param.annotation)
                except ValueError:
                    # Dependency not registered, use default if available
                    if param.default != inspect.Parameter.empty:
                        kwargs[param_name] = param.default
                    else:
                        raise ValueError(
                            f"Cannot resolve dependency {param.annotation} "
                            f"for parameter {param_name} in {cls}"
                        )

        return cls(**kwargs)

    def create_scope(self) -> "DependencyContainer":
        """
        Create a scoped container for request/transaction isolation.
        Inherits registrations but maintains separate scoped instances.
        """
        scoped_container = DependencyContainer()
        scoped_container._services = self._services.copy()
        scoped_container._singletons = self._singletons.copy()
        return scoped_container

    def clear_scoped(self):
        """Clear scoped instances (call at end of request/transaction)."""
        self._scoped_instances.clear()


# Global container instance
_container: Optional[DependencyContainer] = None


def get_container() -> DependencyContainer:
    """Get the global dependency container."""
    global _container
    if _container is None:
        _container = DependencyContainer()
    return _container


def set_container(container: DependencyContainer):
    """Set the global dependency container."""
    global _container
    _container = container
