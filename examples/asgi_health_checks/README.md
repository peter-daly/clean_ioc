# Minimal ASGI health server

This example uses the dependency-free `clean_ioc.ext.asgi` integration to run a small ASGI application. Health checks
are application code rather than behavior built into the extension.

It exposes:

- `GET /health/liveness` — `200` while the process can serve requests;
- `GET /health/readiness` — `200` after startup and until shutdown begins;
- `GET /health/startup` — `200` after startup completes.

Run it with any lifespan-capable ASGI server. For example:

```bash
uv run --with uvicorn uvicorn examples.asgi_health_checks.main:app
```

The example deliberately implements routing and responses directly against the ASGI protocol. A real application can
replace `HealthApplication` with its own router while retaining `CleanIocMiddleware` and `get_scope()`. Each route
resolves a dedicated `LivenessCheck`, `ReadinessCheck`, or `StartupCheck` component; Clean IoC injects the shared
`HealthStatus` dependency into that check.
