from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field

from clean_ioc import Container, Lifespan
from clean_ioc.ext.fastapi import Resolve, add_container_to_app

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
    container = Container()

    # Infrastructure ownership is explicit at the composition root.
    container.register(OrderRepository, InMemoryOrderRepository, lifespan=Lifespan.scoped)
    container.register(PaymentGateway, FakePaymentGateway, lifespan=Lifespan.singleton)
    container.register(AuditSink, LoggingAuditSink, lifespan=Lifespan.singleton)

    # Application code has no FastAPI or Clean IoC imports.
    container.register(CreateOrder)
    container.register_decorator(CreateOrder, AuditedCreateOrder, decorated_arg="wrapped")

    # Fail during startup if the application graph is incomplete or unsafe.
    container.validate(CreateOrder)
    return container


def create_app() -> FastAPI:
    container = build_container()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with add_container_to_app(app, container):
            yield

    app = FastAPI(title="Clean IoC Orders", lifespan=lifespan)

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
