from dataclasses import dataclass
from typing import Protocol

from .domain import CreateOrderCommand, Order


class OrderRepository(Protocol):
    async def add(self, order: Order) -> None: ...


class PaymentGateway(Protocol):
    async def charge(self, customer_id: str, total_pence: int) -> str: ...


class AuditSink(Protocol):
    def record(self, event: str) -> None: ...


@dataclass(frozen=True)
class OrderReceipt:
    order_id: str
    payment_id: str


class CreateOrder:
    """A framework-independent application use case."""

    def __init__(self, repository: OrderRepository, payments: PaymentGateway):
        self.repository = repository
        self.payments = payments

    async def __call__(self, command: CreateOrderCommand) -> OrderReceipt:
        payment_id = await self.payments.charge(command.customer_id, command.total_pence)
        order = Order(
            id=f"order-{payment_id}",
            customer_id=command.customer_id,
            total_pence=command.total_pence,
            payment_id=payment_id,
        )
        await self.repository.add(order)
        return OrderReceipt(order_id=order.id, payment_id=payment_id)


class AuditedCreateOrder:
    """Cross-cutting behavior applied without changing the use case."""

    def __init__(self, wrapped: CreateOrder, audit: AuditSink):
        self.wrapped = wrapped
        self.audit = audit

    async def __call__(self, command: CreateOrderCommand) -> OrderReceipt:
        self.audit.record(f"creating-order:{command.customer_id}")
        receipt = await self.wrapped(command)
        self.audit.record(f"created-order:{receipt.order_id}")
        return receipt
