#!/usr/bin/env python3
"""Seed business data (customers, orders, tickets, interactions, refunds) into PostgreSQL.

Usage: python scripts/seed_business_data.py
"""

import sys
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.db import init_db, async_session_factory
from src.models.customer import Customer
from src.models.order import Order, OrderItem
from src.models.ticket import Ticket
from src.models.customer_interaction import CustomerInteraction
from src.models.refund import Refund


async def seed():
    print("Initializing database...")
    await init_db()
    print("Database ready")

    async with async_session_factory() as session:
        from sqlalchemy import select, func

        existing = await session.execute(select(func.count()).select_from(Customer))
        if existing.scalar() > 0:
            print("Business data already seeded, skipping.")
            return

        # ── Customers ──────────────────────────────────────────────
        c1 = Customer(name="张三", phone="13800001234", email="zhangsan@example.com", vip_level=2, total_orders=15)
        c2 = Customer(name="李四", phone="13900005678", email="lisi@example.com", vip_level=1, total_orders=5)
        c3 = Customer(name="王五", phone="13600009999", email="wangwu@example.com", vip_level=0, total_orders=0)
        c4 = Customer(name="赵六", phone="13700008888", email="zhaoliu@example.com", vip_level=3, total_orders=47)

        session.add_all([c1, c2, c3, c4])
        await session.flush()
        print(f"Seeded 4 customers")

        # ── Orders ─────────────────────────────────────────────────
        o1 = Order(
            order_no="ORD-20250101-0001", customer_id=c1.id, status="shipped",
            total_amount=299.00, shipping_address="北京市朝阳区xxx路100号", tracking_number="SF1234567890",
            created_at=datetime(2025, 5, 1, 10, 30, 0),
        )
        o2 = Order(
            order_no="ORD-20250215-0002", customer_id=c1.id, status="delivered",
            total_amount=697.00, shipping_address="上海市浦东新区xxx路200号", tracking_number="YT9876543210",
            created_at=datetime(2025, 5, 8, 14, 0, 0),
        )
        o3 = Order(
            order_no="ORD-20250401-0003", customer_id=c2.id, status="paid",
            total_amount=1299.00, shipping_address="广州市天河区xxx路300号",
            created_at=datetime(2025, 5, 12, 9, 15, 0),
        )
        o4 = Order(
            order_no="ORD-20250420-0004", customer_id=c1.id, status="delivered",
            total_amount=89.00, shipping_address="北京市朝阳区xxx路100号", tracking_number="ZT1111111111",
            created_at=datetime(2025, 5, 3, 16, 0, 0),
        )
        o5 = Order(
            order_no="ORD-20250501-0005", customer_id=c2.id, status="cancelled",
            total_amount=199.00, shipping_address="深圳市南山区xxx路500号",
            created_at=datetime(2025, 4, 25, 11, 0, 0),
        )

        session.add_all([o1, o2, o3, o4, o5])
        await session.flush()
        print(f"Seeded 5 orders")

        # ── Order Items ─────────────────────────────────────────────
        items = [
            OrderItem(order_id=o1.id, product_name="无线蓝牙耳机 Pro", sku="SKU-001", quantity=1, price=299.00),
            OrderItem(order_id=o2.id, product_name="机械键盘 K8", sku="SKU-008", quantity=1, price=599.00),
            OrderItem(order_id=o2.id, product_name="鼠标垫 XXL", sku="SKU-012", quantity=2, price=49.00),
            OrderItem(order_id=o3.id, product_name="智能手表 S3", sku="SKU-020", quantity=1, price=1299.00),
            OrderItem(order_id=o4.id, product_name="USB-C 数据线 2m", sku="SKU-030", quantity=3, price=29.67),
            OrderItem(order_id=o5.id, product_name="手机壳 透明款", sku="SKU-040", quantity=1, price=199.00),
        ]
        session.add_all(items)
        await session.flush()
        print(f"Seeded 6 order items")

        # ── Tickets ─────────────────────────────────────────────────
        t1 = Ticket(
            title="退货申请 - 蓝牙耳机",
            description="客户反映蓝牙耳机连接不稳定，要求退货退款",
            category="after_sales", priority="medium", status="open",
            customer_id=c1.id, tags=["return", "quality_issue"],
        )
        t2 = Ticket(
            title="支付失败",
            description="客户反映支付页面提示错误，无法完成支付",
            category="order_service", priority="high", status="in_progress",
            customer_id=c2.id, tags=["payment", "technical"],
        )
        t3 = Ticket(
            title="账户登录异常",
            description="客户反映多次尝试登录失败，怀疑账号被盗",
            category="account", priority="urgent", status="resolved",
            customer_id=c4.id, tags=["security", "login"],
            resolved_at=datetime(2025, 5, 16, 10, 0, 0),
        )
        session.add_all([t1, t2, t3])
        await session.flush()
        print(f"Seeded 3 tickets")

        # ── Customer Interactions ───────────────────────────────────
        interactions = [
            CustomerInteraction(
                customer_id=c1.id, interaction_type="chat",
                summary="询问退货政策 - 7天无理由退货流程",
                created_at=datetime(2025, 5, 10, 14, 30, 0),
            ),
            CustomerInteraction(
                customer_id=c1.id, interaction_type="chat",
                summary="订单ORD-20250101-0001查询 - 物流状态",
                created_at=datetime(2025, 5, 12, 9, 0, 0),
            ),
            CustomerInteraction(
                customer_id=c1.id, interaction_type="chat",
                summary="蓝牙耳机退货申请 - 已创建工单TK-*",
                created_at=datetime(2025, 5, 15, 16, 45, 0),
            ),
            CustomerInteraction(
                customer_id=c2.id, interaction_type="phone",
                summary="电话咨询智能手表功能对比 - 已推荐S3型号",
                created_at=datetime(2025, 5, 11, 10, 0, 0),
            ),
            CustomerInteraction(
                customer_id=c2.id, interaction_type="chat",
                summary="支付失败问题 - 已创建紧急工单，转技术团队处理",
                created_at=datetime(2025, 5, 14, 20, 15, 0),
            ),
        ]
        session.add_all(interactions)
        await session.flush()
        print(f"Seeded 5 customer interactions")

        # ── Refunds ─────────────────────────────────────────────────
        r1 = Refund(
            refund_no="REF-20250510-0001", order_id=o4.id, customer_id=c1.id,
            amount=89.00, reason="数据线接触不良，已退货",
            status="completed",
            created_at=datetime(2025, 5, 10, 11, 0, 0),
        )
        session.add(r1)
        await session.flush()
        print(f"Seeded 1 refund")

        # ── Commit ──────────────────────────────────────────────────
        await session.commit()
        print(f"\nSeed complete: 4 customers, 5 orders, 6 items, 3 tickets, 5 interactions, 1 refund")


if __name__ == "__main__":
    asyncio.run(seed())
