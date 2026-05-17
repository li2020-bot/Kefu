"""Tests for data models."""

from src.models.conversation import Conversation, Message, MessageRole
from src.models.ticket import Ticket, TicketCategory, TicketPriority, TicketStatus


class TestConversation:
    def test_create_conversation(self):
        conv = Conversation(tenant_id="test")
        assert conv.id is not None
        assert conv.status == "active"
        assert len(conv.messages) == 0

    def test_add_message(self):
        conv = Conversation()
        msg = Message(role=MessageRole.USER, content="你好")
        conv.add_message(msg)
        assert len(conv.messages) == 1
        assert conv.messages[0].content == "你好"

    def test_message_to_langchain(self):
        msg = Message(role=MessageRole.USER, content="我想退货")
        lc = msg.to_langchain()
        assert lc["role"] == "user"
        assert lc["content"] == "我想退货"


class TestTicket:
    def test_create_ticket(self):
        ticket = Ticket(
            title="退货申请",
            description="商品有质量问题需要退货",
            category=TicketCategory.AFTER_SALES,
            priority=TicketPriority.HIGH,
        )
        assert ticket.ticket_no.startswith("TK-")
        assert ticket.status == TicketStatus.OPEN
        assert ticket.to_dict()["category"] == "after_sales"
