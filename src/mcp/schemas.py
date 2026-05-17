"""MCP shared schemas - Pydantic models for tool inputs/outputs."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# --- CRM Schemas ---

class CustomerProfile(BaseModel):
    id: str
    name: str
    phone: str | None = None
    email: str | None = None
    vip_level: int = 0
    total_orders: int = 0
    created_at: str = ""


class CustomerInteraction(BaseModel):
    id: str
    interaction_type: str
    summary: str
    created_at: str


class LookupCustomerInput(BaseModel):
    query: str = Field(description="Customer phone, email, or ID to look up")


class GetCustomerHistoryInput(BaseModel):
    customer_id: str
    limit: int = 10


class UpdateCustomerInput(BaseModel):
    customer_id: str
    updates: dict = Field(description="Fields to update: name, phone, email")


# --- Order Schemas ---

class OrderStatus(str, Enum):
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class OrderItem(BaseModel):
    product_name: str
    sku: str
    quantity: int
    price: float


class OrderDetail(BaseModel):
    id: str
    order_no: str
    status: OrderStatus
    items: list[OrderItem]
    total_amount: float
    shipping_address: str
    tracking_number: str | None = None
    created_at: str = ""


class OrderSummary(BaseModel):
    id: str
    order_no: str
    status: OrderStatus
    total_amount: float
    created_at: str


class RefundEligibility(BaseModel):
    eligible: bool
    reason: str | None = None
    estimated_refund_amount: float | None = None


class RefundResult(BaseModel):
    success: bool
    refund_id: str | None = None
    message: str


# --- Ticket Schemas ---

class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketCategory(str, Enum):
    PRE_SALES = "pre_sales"
    ORDER_SERVICE = "order_service"
    AFTER_SALES = "after_sales"
    ACCOUNT = "account"
    TECHNICAL = "technical"
    COMPLAINT = "complaint"


class Ticket(BaseModel):
    id: str
    ticket_no: str
    title: str
    description: str
    category: TicketCategory
    priority: TicketPriority = TicketPriority.MEDIUM
    status: TicketStatus = TicketStatus.OPEN
    customer_id: str | None = None
    assignee_id: str | None = None
    created_at: str = ""


class CreateTicketInput(BaseModel):
    customer_id: str
    category: TicketCategory
    description: str
    priority: TicketPriority = TicketPriority.MEDIUM
    title: str = ""


class UpdateTicketInput(BaseModel):
    ticket_id: str
    updates: dict = Field(description="Fields to update: status, priority, assignee_id")
