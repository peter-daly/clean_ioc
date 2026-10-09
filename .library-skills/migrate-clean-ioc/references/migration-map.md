# Clean IoC 1 to 2 migration map

V1 combines registration and resolution in `Container`. V2 composes with `ContainerBuilder`, calls `build()`, then resolves from an immutable `Container` or `Scope`. Build validates all public root plans. Move every mutation before build; use `ScopeBuilder` only for genuine child composition and declared scope slots for late values. A failed builder may be fixed and rebuilt; a successful builder cannot be reused.

| V1 | V2 | Review |
| --- | --- | --- |
| `Container()` | `ContainerBuilder()` then `.build()` | Place build after the last declaration. |
| `Lifespan.once_per_graph` | `"per_resolution"` | Scoped/singleton paths cannot capture this lifespan. |
| Other `Lifespan` members | Corresponding strings | V2 also has `"auto"` and scope policy. |
| `dependency_config=` | `arguments=` | Plain fixed values transfer; `DependencySettings` does not. |
| `DependencySettings(filter=f)` | `select(f)` | Rewrite `f` for static `Component` input. |
| `DependencySettings(value_factory=f)` | `derive(f)` | Derivation runs during build, not activation. |
| `EMPTY` from a value factory | `INJECT` from derivation | This compiles a normal injection edge. |
| `RemoveDependencySetting` | `REMOVE` | Used for inherited argument overrides. |
| `registration_filters` / `node_filters` | `component_filters` | One predicate vocabulary over compiled components. |
| `registration_filter=` on decorators/pre-configurations | `when=` | Combine decorator registration and node conditions manually. |
| `parent_node_filter=` | `when=cf.parent(...)` | Check parent and root semantics. |
| `expect_to_be_scoped(T)` | `declare_scope_slot(T)` | Provide the value before resolution starts. |
| `register_generic_subclasses(..., fallback_type=F)` | `register_subclasses(...)` plus `register_fallback(T, F)` | Discovery happens before build. |
| `register_generic_decorator(...)` | `register_decorator(...)` | Check open generic specialization. |
| `add_container_to_app` / `add_*_to_scope` | `FastAPIBundle()` before build, then `install_fastapi` | Review the V2 FastAPI extension's public API. |

Other removed concepts include mutable request scopes, runtime dependency graphs, `Registration`, `DependencyNode`, injected `Registrator`, and compatibility imports from `clean_ioc.core`. Prefer explicit constructor dependencies and `Provider[T]` for known deferred dependencies. Inspect `container.graph` for static plans; it does not expose resolved instances.

The codemod handles only syntax whose location and meaning are clear. Review all findings, and inspect code that creates scopes, installs framework integrations, registers dynamic subclasses, supplies dependency callbacks, or depends on runtime filter execution. Build affected entry points, then exercise resolution and cleanup in application tests.
