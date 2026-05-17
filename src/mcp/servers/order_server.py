"""Order FastMCP Server - order management tools.

Provides tools for: order query, customer orders list, refund eligibility check, refund initiation.
Queries PostgreSQL via async SQLAlchemy sessions.
"""

from datetime import datetime
from uuid import uuid4

from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)

from fastmcp import FastMCP

order_mcp = FastMCP("order-server")


async def _get_order(session, order_id: str):
    """Find an order by UUID or order_no. Returns Order or None."""
    from uuid import UUID
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from src.models.order import Order

    # Try UUID
    try:
        order = await session.get(Order, UUID(order_id), options=[selectinload(Order.items)])
        if order:
            return order
    except (ValueError, AttributeError):
        pass

    # Try order_no
    stmt = select(Order).where(Order.order_no == order_id).options(selectinload(Order.items))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _query_order_impl(order_id: str) -> dict:
    """Query order details by order ID or order number."""
    from src.core.db import async_session_factory

    async with async_session_factory() as session:
        order = await _get_order(session, order_id)
        if not order:
            return {"found": False, "order": None, "message": f"Order {order_id} not found"}
        return {"found": True, "order": order.to_dict()}


async def _list_customer_orders_impl(customer_id: str, status: str | None = None) -> dict:
    """List orders for a customer, optionally filtered by status."""
    from sqlalchemy import select
    from src.core.db import async_session_factory
    from src.models.order import Order

    async with async_session_factory() as session:
        stmt = select(Order).where(Order.customer_id == customer_id)
        if status:
            stmt = stmt.where(Order.status == status)
        stmt = stmt.order_by(Order.created_at.desc())
        result = await session.execute(stmt)
        orders = result.scalars().all()
        return {
            "customer_id": customer_id,
            "total": len(orders),
            "orders": [o.to_summary() for o in orders],
        }


async def _check_refund_eligibility_impl(order_id: str) -> dict:
    """Check if an order is eligible for refund."""
    from src.core.db import async_session_factory

    async with async_session_factory() as session:
        order = await _get_order(session, order_id)
        if not order:
            return {"eligible": False, "reason": f"Order {order_id} not found"}

        status = order.status
        days_since_order = (datetime.now() - order.created_at.replace(tzinfo=None)).days

        if status == "cancelled":
            return {"eligible": False, "reason": "Order already cancelled"}

        if status in ("pending_payment", "paid", "processing"):
            return {
                "eligible": True,
                "estimated_refund_amount": float(order.total_amount),
                "reason": "Order not yet shipped, full refund eligible",
            }

        if status in ("shipped", "delivered"):
            if days_since_order <= 7:
                return {
                    "eligible": True,
                    "estimated_refund_amount": float(order.total_amount),
                    "reason": "Within 7-day return window",
                }
            return {
                "eligible": False,
                "reason": f"Return window expired ({days_since_order} days since order, max 7 days)",
            }

        return {"eligible": False, "reason": f"Unknown order status: {status}"}


async def _initiate_refund_impl(order_id: str, reason: str, amount: float | None = None) -> dict:
    """Initiate a refund for an order."""
    from src.core.db import async_session_factory
    from src.models.refund import Refund

    async with async_session_factory() as session:
        order = await _get_order(session, order_id)
        if not order:
            return {"success": False, "message": f"Order {order_id} not found"}

        refund_no = f"REF-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}"
        refund_amount = amount or float(order.total_amount)

        refund = Refund(
            refund_no=refund_no,
            order_id=order.id,
            customer_id=order.customer_id,
            amount=refund_amount,
            reason=reason,
            status="pending",
        )
        session.add(refund)
        await session.commit()

        logger.info("refund_initiated", order_id=order_id, refund_no=refund_no, amount=refund_amount)

        return {
            "success": True,
            "refund_id": refund_no,
            "order_id": order.order_no,
            "amount": refund_amount,
            "message": f"Refund of {refund_amount} initiated. Expected 3-5 business days to process.",
        }


@order_mcp.tool()
async def query_order(order_id: str) -> dict:
    """Query order details by order ID (e.g., ORD-20250101-0001) or UUID. Returns order status, items, amount, shipping info."""
    return await _query_order_impl(order_id)


@order_mcp.tool()
async def list_customer_orders(customer_id: str, status: str | None = None) -> dict:
    """List all orders for a customer, optionally filtered by status (e.g., paid, shipped, delivered)."""
    return await _list_customer_orders_impl(customer_id, status)


@order_mcp.tool()
async def check_refund_eligibility(order_id: str) -> dict:
    """Check if an order is eligible for refund based on status and 7-day return window."""
    return await _check_refund_eligibility_impl(order_id)


@order_mcp.tool()
async def initiate_refund(order_id: str, reason: str, amount: float | None = None) -> dict:
    """Initiate a refund for an order (write operation). Refund processed in 3-5 business days."""
    return await _initiate_refund_impl(order_id, reason, amount)
