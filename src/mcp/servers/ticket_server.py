"""Ticket FastMCP Server - work order / ticket management tools.

Provides tools for: create ticket, query ticket, update ticket, list tickets.
Queries PostgreSQL via async SQLAlchemy sessions.
"""

import json
from datetime import datetime

from src.core.logging import get_logger as _get_logger
import logging; logger = _get_logger(__name__)

from fastmcp import FastMCP

ticket_mcp = FastMCP("ticket-server")


async def _find_ticket(session, ticket_id: str):
    """Find a ticket by UUID or ticket_no. Returns Ticket or None."""
    from uuid import UUID
    from sqlalchemy import select
    from src.models.ticket import Ticket

    # Try UUID
    try:
        ticket = await session.get(Ticket, UUID(ticket_id))
        if ticket:
            return ticket
    except (ValueError, AttributeError):
        pass

    # Try ticket_no
    stmt = select(Ticket).where(Ticket.ticket_no == ticket_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _create_ticket_impl(
    customer_id: str,
    category: str,
    description: str,
    priority: str = "medium",
    title: str = "",
) -> dict:
    """Create a new support ticket."""
    from src.core.db import async_session_factory
    from src.models.ticket import Ticket

    async with async_session_factory() as session:
        ticket = Ticket(
            title=title or f"[{category}] {description[:50]}",
            description=description,
            category=category,
            priority=priority,
            status="open",
            customer_id=customer_id,
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)

        logger.info("ticket_created", ticket_no=ticket.ticket_no, category=category)
        return ticket.to_dict()


async def _query_ticket_impl(ticket_id: str) -> dict:
    """Query a ticket by ID or ticket number."""
    from src.core.db import async_session_factory

    async with async_session_factory() as session:
        ticket = await _find_ticket(session, ticket_id)
        if not ticket:
            return {"found": False, "ticket": None, "message": f"Ticket {ticket_id} not found"}
        return {"found": True, "ticket": ticket.to_dict()}


async def _update_ticket_impl(ticket_id: str, updates: dict) -> dict:
    """Update ticket fields (status, priority, assignee_id, title, description, tags)."""
    from src.core.db import async_session_factory

    allowed_fields = {"status", "priority", "assignee_id", "title", "description", "tags"}
    filtered = {k: v for k, v in updates.items() if k in allowed_fields}
    if not filtered:
        return {"success": False, "message": "No valid fields to update"}

    async with async_session_factory() as session:
        ticket = await _find_ticket(session, ticket_id)
        if not ticket:
            return {"success": False, "message": f"Ticket {ticket_id} not found"}

        for key, value in filtered.items():
            setattr(ticket, key, value)

        # Auto-set resolution timestamps
        if "status" in filtered:
            if filtered["status"] == "resolved" and not ticket.resolved_at:
                ticket.resolved_at = datetime.now()
            elif filtered["status"] == "closed" and not ticket.closed_at:
                ticket.closed_at = datetime.now()

        await session.commit()
        await session.refresh(ticket)
        return {"success": True, "ticket": ticket.to_dict()}


async def _list_tickets_impl(customer_id: str, status: str | None = None) -> dict:
    """List tickets for a customer, optionally filtered by status."""
    from sqlalchemy import select
    from src.core.db import async_session_factory
    from src.models.ticket import Ticket

    async with async_session_factory() as session:
        stmt = select(Ticket).where(Ticket.customer_id == customer_id)
        if status:
            stmt = stmt.where(Ticket.status == status)
        stmt = stmt.order_by(Ticket.created_at.desc())
        result = await session.execute(stmt)
        tickets = result.scalars().all()

        return {
            "customer_id": customer_id,
            "total": len(tickets),
            "tickets": [t.to_dict() for t in tickets],
        }


@ticket_mcp.tool()
async def create_ticket(
    customer_id: str,
    category: str,
    description: str,
    priority: str = "medium",
    title: str = "",
) -> dict:
    """Create a new support ticket. category: pre_sales/order_service/after_sales/account/technical/complaint. priority: low/medium/high/urgent."""
    return await _create_ticket_impl(customer_id, category, description, priority, title)


@ticket_mcp.tool()
async def query_ticket(ticket_id: str) -> dict:
    """Query a ticket by ID (UUID) or ticket number (e.g., TK-20250517-ABC123)."""
    return await _query_ticket_impl(ticket_id)


@ticket_mcp.tool()
async def update_ticket(ticket_id: str, updates: dict) -> dict:
    """Update ticket fields. Allowed: status, priority, assignee_id, title, description, tags."""
    return await _update_ticket_impl(ticket_id, updates)


@ticket_mcp.tool()
async def list_tickets(customer_id: str, status: str | None = None) -> dict:
    """List all tickets for a customer, optionally filtered by status (open/in_progress/resolved/closed)."""
    return await _list_tickets_impl(customer_id, status)
