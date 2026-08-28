---
description: Decide when Clean IoC is the right Python dependency-injection approach for Clean Architecture, FastAPI, CQRS, and resource-heavy applications.
---

# Why Clean IoC?

Dependency injection is not automatically an improvement. For a small script with three stable objects, direct construction is usually clearer. A container earns its place when the composition root is becoming a system of its own.

## The problem it is designed for

Clean IoC fits applications where several of these are true:

- domain and application code must remain independent of FastAPI, a worker framework, or a CLI;
- implementations differ by environment, tenant, consuming service, name, or tag;
- database sessions, clients, and units of work have different ownership boundaries;
- handler or event-consumer families use closed generic types;
- logging, metrics, retries, or authorization should wrap services consistently;
- async factories and cleanup need to compose with synchronous application objects;
- reviewers need to understand and verify a deep graph without running it.

The container is configured once at the application boundary. Ordinary code continues to use ordinary constructors.

## Compare the approaches

| Approach | Strength | Trade-off |
| --- | --- | --- |
| Manual wiring | Maximum explicitness and no library | Composition becomes repetitive as graphs and variants grow |
| Service dictionary / locator | Very small implementation | Dependencies become hidden runtime lookups throughout application code |
| Framework-native injection | Excellent at the framework boundary | Domain services can become coupled to framework concepts |
| Clean IoC | Typed, portable plans with explicit ownership and build-time compilation | Adds a composition layer that small applications may not need |

Clean IoC does not try to replace a framework's transport features. In FastAPI, for example, request parsing and transport-level dependencies remain FastAPI concerns; Clean IoC constructs portable application services inside a request scope.

## Why not just wire objects manually?

Manual wiring remains a good default. The inflection point comes when ownership and selection matter as much as construction:

```python
# This is easy...
service = Checkout(SqlOrderRepository(session), StripeGateway(client))

# ...until the real composition root also owns request sessions, client pools,
# tenant-specific gateways, handler collections, decorators, and cleanup.
```

Clean IoC centralizes those rules and compiles them before activation. The gain is not saving constructor lines; it is making architecture-level wiring consistent, inspectable, and cheap to execute repeatedly.

## Why type-driven registration?

Python type hints already describe the dependency contract. Clean IoC uses them without requiring application classes to inherit from library types or carry injection decorators.

That creates a useful boundary:

- the application owns interfaces and behavior;
- infrastructure owns implementations;
- the composition root owns selection and lifetime;
- Clean IoC owns component-plan compilation, activation, and cleanup.

## The confidence loop

```mermaid
flowchart LR
    register["Register at composition root"]
    validate["Build without activating"]
    explain["Review static components"]
    resolve["Resolve at the boundary"]
    cleanup["Release at the owning scope"]
    register --> validate --> explain --> resolve --> cleanup
```

That loop is the central reason to choose Clean IoC over a runtime registry: the builder fails fast when static rules are unsafe and the container executes the frozen result without rebuilding dependency graphs.

## When not to use it

Prefer direct construction when:

- the graph is small and stable;
- every dependency shares the same obvious lifetime;
- there is one implementation of each abstraction;
- runtime selection, generic discovery, and decorators are unnecessary;
- adding registration would obscure rather than clarify the program.

A good composition root should make an application's architecture easier to see. If the container configuration is harder to understand than direct constructors, simplify it.
