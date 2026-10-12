from uuid import uuid4

from .domain import Order


class InMemoryOrderRepository:
    def __init__(self):
        self.orders: list[Order] = []

    async def add(self, order: Order) -> None:
        self.orders.append(order)


class FakePaymentGateway:
    async def charge(self, customer_id: str, total_pence: int) -> str:
        return f"payment-{uuid4().hex[:8]}"


class LoggingAuditSink:
    def __init__(self):
        self.events: list[str] = []

    def record(self, event: str) -> None:
        self.events.append(event)
