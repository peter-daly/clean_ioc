from fastapi import FastAPI
from pydantic import BaseModel, Field

from clean_ioc import Container, ContainerBuilder
from clean_ioc.ext.fastapi import Resolve, install_fastapi

from .application import (
    AuditedCreateOrder,
    AuditSink,
    CreateOrder,
    OrderReceipt,
    OrderRepository,
    PaymentGateway,
)
from .domain import CreateOrderCommand
from .infrastructure import FakePaymentGateway, InMemoryOrderRepository, LoggingAuditSink


class CreateOrderRequest(BaseModel):
    customer_id: str
    total_pence: int = Field(gt=0)


def build_container() -> Container:
    builder = ContainerBuilder()

    # Infrastructure ownership is explicit at the composition root.
    builder.register(OrderRepository, InMemoryOrderRepository, lifespan="scoped")
    builder.register(PaymentGateway, FakePaymentGateway, lifespan="singleton")
    builder.register(AuditSink, LoggingAuditSink, lifespan="singleton")

    # Application code has no FastAPI or Clean IoC imports.
    builder.register(CreateOrder)
    builder.register_decorator(CreateOrder, AuditedCreateOrder, decorated_arg="wrapped")

    # Fail during startup if the application graph is incomplete or unsafe.
    return builder.build()


def create_app() -> FastAPI:
    container = build_container()
    app = FastAPI(title="Clean IoC Orders")
    install_fastapi(app, container)

    @app.post("/orders", response_model=OrderReceipt)
    async def create_order(
        request: CreateOrderRequest,
        handler: CreateOrder = Resolve(CreateOrder),
    ) -> OrderReceipt:
        return await handler(
            CreateOrderCommand(
                customer_id=request.customer_id,
                total_pence=request.total_pence,
            )
        )

    return app


app = create_app()
