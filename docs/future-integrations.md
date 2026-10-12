---
description: Candidate Clean IoC integrations for task workers, command-line applications, RPC services, and web frameworks.
---

# Potential future integrations

Clean IoC is most useful when the same compiled application graph can run behind more than one delivery mechanism. An
integration should therefore do more than add another spelling for dependency lookup. It should define a clear runtime
boundary, supply framework-owned values through declared scope slots, retain scopes for the complete operation, and
validate component entry points before work is accepted.

The APIs on this page are design sketches, not currently supported interfaces or release commitments.

## Celery

Celery is the leading candidate. A worker task is a natural scope boundary, and a Celery integration would demonstrate
that application services compiled for an HTTP API can be reused unchanged in background work.

The proposed model treats each task handler as an ordinary registered component. Constructor parameters are application
dependencies; only parameters passed to `__call__` are serialized into the Celery message.

```python
from celery import Celery

from clean_ioc import ContainerBuilder
from clean_ioc.ext.celery import CeleryIntegration


celery = Celery(
    "billing",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
)
ioc = CeleryIntegration(celery)


@ioc.task(
    name="billing.send_invoice",
    queue="billing",
    autoretry_for=(TemporaryEmailFailure,),
    retry_backoff=True,
    max_retries=5,
)
class SendInvoiceTask:
    def __init__(
        self,
        invoices: InvoiceRepository,
        email: EmailClient,
        audit: AuditLog,
    ):
        self.invoices = invoices
        self.email = email
        self.audit = audit

    def __call__(self, invoice_id: str) -> None:
        invoice = self.invoices.get(invoice_id)
        self.email.send_invoice(invoice)
        self.audit.invoice_sent(invoice_id)
```

The integration would add its boundary components and complete the build in one explicit operation:

```python
builder = ContainerBuilder()
builder.register(Database, factory=create_database, lifespan="singleton")
builder.register(InvoiceRepository, SqlInvoiceRepository, lifespan="scoped")
builder.register(EmailClient, lifespan="singleton")
builder.register(AuditLog, lifespan="scoped")

container = ioc.build(builder)
```

`ioc.build(builder)` would declare Celery runtime slots, register every decorated task component, mark those components
as entry points, build the container, and bind the frozen container to the worker integration. It would not construct
singletons during import. Task invocation would remain standard Celery:

```python
SendInvoiceTask.delay("invoice-123")
```

The intended lifecycle mapping is:

| Celery boundary | Clean IoC ownership |
| --- | --- |
| Worker child process starts | Enter the root container |
| Task begins | Create a child scope |
| Task metadata becomes available | Provide a declared `CeleryTaskContext` slot |
| Task executes | Resolve and invoke the task component |
| Task succeeds, fails, or retries | Close the task scope |
| Worker child process exits | Close the root container and its singletons |

This design deliberately avoids `@inject` and `Resolve`. The integration owns the complete task adapter, so constructor
injection is sufficient. Keeping dependencies out of the callable task signature also prevents application objects from
being mistaken for broker arguments.

Important design work would include prefork ownership, cleanup during retries and worker termination, eager execution in
tests, task signature preservation, and a defined policy for asynchronous factories in otherwise synchronous workers.

## Click and Typer

A command invocation is another clear scope boundary. A command component could receive application dependencies through
its constructor while its `__call__` parameters remain ordinary command-line arguments.

This would provide a low-overhead way to reuse the same graph for administrative commands, migrations, scheduled jobs,
and local tools. The main design work is preserving Click and Typer parameter discovery while keeping injected
constructor dependencies out of the command signature.

## gRPC

For gRPC, a server would own the root container and each unary call or streaming session would own a child scope. Request
objects, RPC context, metadata, and response metadata could be declared boundary slots. An interceptor could resolve a
handler component and retain its scope until the response or stream completes.

The integration would need separate, well-tested behavior for synchronous gRPC and `grpc.aio`, including cancellation,
deadlines, client-streaming, server-streaming, and bidirectional streams.

## Django

Django middleware could create a scope for each request, while view adapters and management commands resolve compiled
entry points. This would bring Clean IoC to a large ecosystem, but it has a less uniform ownership model than an ASGI-only
application. A complete design would need to cover synchronous and asynchronous views, class-based views, streaming
responses, management commands, and deterministic singleton cleanup under both WSGI and ASGI deployment.

## aiohttp and Quart

Both frameworks provide useful asynchronous application and request boundaries. An integration could own the root
container through application startup and cleanup, create request or WebSocket scopes in middleware, and resolve handler
components at the transport boundary.

These integrations are technically direct, although they would add less differentiation than demonstrating one graph
across an API, a Celery worker, and a CLI.

## Litestar

Litestar already provides a substantial dependency-injection system. A Clean IoC integration would therefore need a
specific purpose: compiled application graphs shared with non-HTTP entry points, consistent lifespan validation, or
framework-independent decorators and generic handlers. Without that distinction, the integration would duplicate native
framework capabilities rather than establish a useful boundary.

## Evaluation criteria

Before promoting any candidate to a supported extension, its design should answer four questions:

1. What owns the root container, and when is it closed?
2. What constitutes one child scope, including streaming, cancellation, retries, and background work?
3. Which framework values must be declared and supplied as runtime slots?
4. Which entry points and filters can be validated before the framework accepts work?

An integration should remain thin. Application components should continue to use ordinary constructors and remain
resolvable without importing the framework adapter.
