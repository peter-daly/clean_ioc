from dataclasses import dataclass


@dataclass(frozen=True)
class CreateOrderCommand:
    customer_id: str
    total_pence: int


@dataclass(frozen=True)
class Order:
    id: str
    customer_id: str
    total_pence: int
    payment_id: str
