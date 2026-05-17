"""Authentication middleware for API routes."""

from fastapi import Header, HTTPException, Request


async def verify_tenant(request: Request):
    """Verify tenant identity from request headers.

    In production: Validate JWT token and extract tenant_id.
    """
    tenant_id = request.headers.get("X-Tenant-ID", "default")
    return tenant_id


async def verify_api_key(x_api_key: str = Header(None)):
    """Verify API key for external API access."""
    # In production: validate against API key store
    if x_api_key is None:
        # Allow requests without API key in debug mode
        return None
    return x_api_key
