"""
Feature Flag Middleware
Routes traffic between v1 (legacy) and v2 (new architecture) based on configuration.
"""

import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class ArchitectureRoutingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to route requests between v1 and v2 architectures.
    
    Routing Strategy:
    - Explicit /api/v2/* → Always use v2
    - Explicit /api/v1/* → Always use v1  
    - /api/* (no version) → Check feature flag
    """
    
    def __init__(self, app, default_version: str = "v1"):
        super().__init__(app)
        self.default_version = default_version
        logger.info(f"Architecture routing middleware initialized (default: {default_version})")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        
        # Log routing decision
        if path.startswith("/api/v2/"):
            logger.debug(f"Routing to v2: {path}")
        elif path.startswith("/api/v1/"):
            logger.debug(f"Routing to v1: {path}")
        elif path.startswith("/api/"):
            logger.debug(f"Routing to {self.default_version}: {path}")
        
        # Continue processing
        response = await call_next(request)
        
        # Add header indicating which architecture served the request
        if path.startswith("/api/v2/"):
            response.headers["X-Architecture-Version"] = "v2"
        elif path.startswith("/api/v1/") or path.startswith("/api/"):
            response.headers["X-Architecture-Version"] = "v1"
        
        return response


def get_architecture_version_for_tenant(tenant_id: str) -> str:
    """
    Determine which architecture version to use for a specific tenant.
    
    This can be extended to:
    - Query database for tenant preferences
    - Use LaunchDarkly or similar feature flag service
    - Apply A/B testing logic
    - Check environment variables
    
    For now, uses environment variable.
    """
    import os
    
    # Check environment override
    use_v2 = os.getenv("USE_V2_ARCHITECTURE", "false").lower() == "true"
    
    # TODO: Add tenant-specific overrides
    # tenant_config = get_tenant_config(tenant_id)
    # if tenant_config.get("use_v2"):
    #     return "v2"
    
    return "v2" if use_v2 else "v1"
