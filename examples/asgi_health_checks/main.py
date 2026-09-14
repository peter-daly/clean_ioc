from __future__ import annotations

from dataclasses import dataclass

from clean_ioc import Container, ContainerBuilder
from clean_ioc.ext.asgi import (
    ASGIMessage,
    ASGIScope,
    CleanIocMiddleware,
    Receive,
    Send,
    get_scope,
)


@dataclass(slots=True)
class HealthStatus:
    """Application-owned health state; this is not part of the ASGI extension."""

    alive: bool = True
    started: bool = False
    ready: bool = False


class LivenessCheck:
    def __init__(self, status: HealthStatus):
        self.status = status

    def __call__(self) -> bool:
        return self.status.alive


class ReadinessCheck:
    def __init__(self, status: HealthStatus):
        self.status = status

    def __call__(self) -> bool:
        return self.status.ready


class StartupCheck:
    def __init__(self, status: HealthStatus):
        self.status = status

    def __call__(self) -> bool:
        return self.status.started


class HealthApplication:
    """A minimal ASGI application with three Kubernetes-style health routes."""

    def __init__(self, status: HealthStatus):
        self.status = status

    async def __call__(self, scope: ASGIScope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self._lifespan(receive, send)
            return

        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1000})
            return

        if scope["type"] != "http":
            return

        method = str(scope.get("method", "GET")).upper()
        path = scope.get("path")
        check_type = {
            "/health/liveness": LivenessCheck,
            "/health/readiness": ReadinessCheck,
            "/health/startup": StartupCheck,
        }.get(path)
        if check_type is None:
            await self._respond(send, 404, b'{"detail":"Not Found"}', head=method == "HEAD")
            return
        if method not in ("GET", "HEAD"):
            await self._respond(send, 405, b'{"detail":"Method Not Allowed"}', head=False)
            return

        # Each route resolves its own check, including the check's HealthStatus dependency.
        check = await get_scope(scope).resolve_async(check_type)
        healthy = check()
        body = b'{"status":"ok"}' if healthy else b'{"status":"unavailable"}'
        await self._respond(send, 200 if healthy else 503, body, head=method == "HEAD")

    async def _lifespan(self, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                # Real applications can perform initialization before becoming ready.
                self.status.started = True
                self.status.ready = True
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                self.status.ready = False
                await send({"type": "lifespan.shutdown.complete"})
                return

    @staticmethod
    async def _respond(send: Send, status: int, body: bytes, *, head: bool) -> None:
        headers: list[tuple[bytes, bytes]] = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"cache-control", b"no-store"),
        ]
        start: ASGIMessage = {
            "type": "http.response.start",
            "status": status,
            "headers": headers,
        }
        await send(start)
        await send({"type": "http.response.body", "body": b"" if head else body})


def build_container(status: HealthStatus) -> Container:
    builder = ContainerBuilder()
    builder.register(HealthStatus, instance=status, lifespan="singleton")
    builder.register(LivenessCheck)
    builder.register(ReadinessCheck)
    builder.register(StartupCheck)
    return builder.build()


def create_app() -> CleanIocMiddleware:
    status = HealthStatus()
    application = HealthApplication(status)
    return CleanIocMiddleware(application, root_scope=build_container(status))


app = create_app()
