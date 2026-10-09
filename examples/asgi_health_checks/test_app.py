import asyncio
from typing import Any

import pytest

from .main import (
    HealthStatus,
    LivenessCheck,
    ReadinessCheck,
    StartupCheck,
    build_container,
    create_app,
)


def _http_scope(path: str, method: str = "GET") -> dict[str, Any]:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": [],
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "root_path": "",
    }


async def _request(app, path: str, method: str = "GET") -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(dict(message))

    await app(_http_scope(path, method), receive, send)
    return messages


def _status(messages: list[dict[str, Any]]) -> int:
    return next(message["status"] for message in messages if message["type"] == "http.response.start")


def test_each_health_check_receives_its_dependency_from_the_container():
    status = HealthStatus()
    with build_container(status) as container:
        with container.new_scope() as scope:
            checks = (
                scope.resolve(LivenessCheck),
                scope.resolve(ReadinessCheck),
                scope.resolve(StartupCheck),
            )

    assert all(check.status is status for check in checks)


@pytest.mark.asyncio
async def test_health_routes_reflect_the_example_application_lifecycle():
    app = create_app()

    assert _status(await _request(app, "/health/liveness")) == 200
    assert _status(await _request(app, "/health/readiness")) == 503
    assert _status(await _request(app, "/health/startup")) == 503

    received: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    sent: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def send(message):
        await sent.put(dict(message))

    lifespan_task = asyncio.create_task(
        app(
            {"type": "lifespan", "asgi": {"version": "3.0"}, "state": {}},
            received.get,
            send,
        )
    )
    await received.put({"type": "lifespan.startup"})
    assert await sent.get() == {"type": "lifespan.startup.complete"}

    assert _status(await _request(app, "/health/liveness")) == 200
    assert _status(await _request(app, "/health/readiness")) == 200
    assert _status(await _request(app, "/health/startup")) == 200
    assert _status(await _request(app, "/missing")) == 404
    assert _status(await _request(app, "/health/liveness", "POST")) == 405

    await received.put({"type": "lifespan.shutdown"})
    assert await sent.get() == {"type": "lifespan.shutdown.complete"}
    await lifespan_task
