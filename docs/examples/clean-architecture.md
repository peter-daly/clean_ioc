---
description: A runnable FastAPI Clean Architecture example with ports, adapters, request scopes, decorators, and build-time compilation.
---

# FastAPI Clean Architecture example

The repository includes a [runnable order API](https://github.com/peter-daly/clean_ioc/tree/main/examples/fastapi_clean_architecture) that demonstrates where Clean IoC belongs in a layered application.

```mermaid
flowchart LR
    http["FastAPI endpoint"]
    usecase["CreateOrder use case"]
    ports["Repository + payment ports"]
    adapters["Infrastructure adapters"]
    http --> usecase --> ports
    adapters -. implement .-> ports
    composition["Composition root"] -. wires and validates .-> usecase
    composition -. selects .-> adapters
```

## Boundaries

The example is split by responsibility:

| File | Owns | Framework imports? |
| --- | --- | --- |
| `domain.py` | Order data | No |
| `application.py` | Ports, use case, audit decorator | No |
| `infrastructure.py` | Repository, payment, and audit adapters | No |
| `main.py` | FastAPI routes and Clean IoC registrations | Yes—this is the boundary |

The core use case receives typed ports through its constructor:

```python
class CreateOrder:
    def __init__(self, repository: OrderRepository, payments: PaymentGateway):
        self.repository = repository
        self.payments = payments
```

No application class performs a container lookup.

## Composition root

```python
builder = ContainerBuilder()
builder.register(OrderRepository, InMemoryOrderRepository, lifespan=Lifespan.scoped)
builder.register(PaymentGateway, FakePaymentGateway, lifespan=Lifespan.singleton)
builder.register(AuditSink, LoggingAuditSink, lifespan=Lifespan.singleton)
builder.register(CreateOrder)
builder.register_decorator(CreateOrder, AuditedCreateOrder, decorated_arg="wrapped")

container = builder.build()

app = FastAPI()
install_fastapi(app, container)
```

This is the only place that chooses concrete adapters and ownership. `build()` proves that the use case and its decorator are complete and compiles their runtime instructions. `install_fastapi()` owns the container lifespan, creates request scopes, and validates the route's `Resolve(CreateOrder)` selection before FastAPI accepts traffic.

## Request boundary

```python
@app.post("/orders")
async def create_order(
    request: CreateOrderRequest,
    handler: CreateOrder = Resolve(CreateOrder),
):
    return await handler(CreateOrderCommand(**request.model_dump()))
```

`Resolve(CreateOrder)` asks the current request scope for the application entry point. The repository is created once for that request; singleton adapters live until application shutdown.

## Run it

```bash
uv run fastapi dev examples/fastapi_clean_architecture/main.py
```

The example includes an end-to-end `TestClient` test and is exercised by the repository test suite.
