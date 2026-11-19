# Minimal ASGI health server

The repository's
[`examples/asgi_health_checks`](https://github.com/peter-daly/clean_ioc/tree/main/examples/asgi_health_checks)
is a dependency-free ASGI application wrapped by `CleanIocMiddleware`.

Its routes are example application policy, not part of `clean_ioc.ext.asgi`:

| Route | Meaning |
| --- | --- |
| `/health/liveness` | The process is able to serve a request |
| `/health/readiness` | Application startup completed and shutdown has not begun |
| `/health/startup` | Application startup completed successfully |

The application changes its readiness and startup state while handling ASGI lifespan messages. Each HTTP probe uses
the operation scope installed by `CleanIocMiddleware` to resolve a dedicated `LivenessCheck`, `ReadinessCheck`, or
`StartupCheck` component. The compiled container injects the shared `HealthStatus` dependency into each check.

Run the example with any lifespan-capable ASGI server. For example:

```bash
uv run --with uvicorn uvicorn examples.asgi_health_checks.main:app
```

No server dependency is added to Clean IoC itself.
