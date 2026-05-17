"""CRM FastMCP Server - customer relationship management tools.

Provides tools for: customer lookup, history retrieval, profile updates.
Queries PostgreSQL via async SQLAlchemy sessions.
"""

from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)

from fastmcp import FastMCP

crm_mcp = FastMCP("crm-server")


async def _lookup_customer_impl(query: str) -> dict:
    """Look up a customer by phone, email, or ID."""
    from uuid import UUID
    from sqlalchemy import select, or_
    from src.core.db import async_session_factory
    from src.models.customer import Customer

    async with async_session_factory() as session:
        # Try exact UUID match first
        try:
            customer = await session.get(Customer, UUID(query))
            if customer:
                return {"found": True, "customer": customer.to_dict()}
        except (ValueError, AttributeError):
            pass

        # Search by phone or email
        stmt = select(Customer).where(
            or_(Customer.phone == query, Customer.email == query)
        ).limit(1)
        result = await session.execute(stmt)
        customer = result.scalar_one_or_none()
        if customer:
            return {"found": True, "customer": customer.to_dict()}

    return {"found": False, "customer": None}


async def _get_customer_history_impl(customer_id: str, limit: int = 10) -> dict:
    """Get recent interaction history for a customer."""
    from sqlalchemy import select, desc
    from src.core.db import async_session_factory
    from src.models.customer_interaction import CustomerInteraction

    async with async_session_factory() as session:
        stmt = (
            select(CustomerInteraction)
            .where(CustomerInteraction.customer_id == customer_id)
            .order_by(desc(CustomerInteraction.created_at))
            .limit(limit)
        )
        result = await session.execute(stmt)
        interactions = result.scalars().all()
        return {
            "customer_id": customer_id,
            "total": len(interactions),
            "interactions": [i.to_dict() for i in interactions],
        }


async def _update_customer_profile_impl(customer_id: str, updates: dict) -> dict:
    """Update customer profile fields (name, phone, email only)."""
    from src.core.db import async_session_factory
    from src.models.customer import Customer

    allowed_fields = {"name", "phone", "email"}
    filtered = {k: v for k, v in updates.items() if k in allowed_fields}
    if not filtered:
        return {"success": False, "message": "No valid fields to update"}

    async with async_session_factory() as session:
        customer = await session.get(Customer, customer_id)
        if not customer:
            return {"success": False, "message": f"Customer {customer_id} not found"}

        for key, value in filtered.items():
            setattr(customer, key, value)

        await session.commit()
        await session.refresh(customer)
        return {"success": True, "customer": customer.to_dict()}


@crm_mcp.tool()
async def lookup_customer(query: str) -> dict:
    """Look up a customer by phone, email, or ID. Returns customer profile with vip_level, total_orders, etc."""
    return await _lookup_customer_impl(query)


@crm_mcp.tool()
async def get_customer_history(customer_id: str, limit: int = 10) -> dict:
    """Get recent interaction history for a customer (chats, calls, tickets)."""
    return await _get_customer_history_impl(customer_id, limit)


@crm_mcp.tool()
async def update_customer_profile(customer_id: str, updates: dict) -> dict:
    """Update customer profile fields. Allowed fields: name, phone, email."""
    return await _update_customer_profile_impl(customer_id, updates)
