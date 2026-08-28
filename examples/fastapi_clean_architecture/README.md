# FastAPI + Clean Architecture

This runnable example keeps business behavior independent of FastAPI and Clean IoC:

- `domain.py` contains data with no external dependencies;
- `application.py` owns ports, the use case, and an audit decorator;
- `infrastructure.py` implements those ports;
- `main.py` is the composition root and HTTP adapter;
- `test_app.py` exercises the entire lifespan and request scope.

Run it from the repository root:

```bash
uv run fastapi dev examples/fastapi_clean_architecture/main.py
```

Then create an order:

```bash
curl -X POST http://127.0.0.1:8000/orders \
  -H 'content-type: application/json' \
  -d '{"customer_id":"customer-123","total_pence":2500}'
```

The composition root calls `builder.build()` before serving requests. That validates and compiles the application plan without running user constructors. Each request gets one scoped repository, while the payment gateway and audit sink belong to the application container.
