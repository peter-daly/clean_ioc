# GitHub repository profile

Apply these settings in **GitHub → About → Edit repository details** after the local changes are published.

## About

**Description**

> Compile typed Python dependency plans before startup, then resolve from an immutable runtime. Explicit lifespans, generics, decorators, and FastAPI scopes.

**Website**

> https://peter-daly.github.io/clean_ioc/

**Topics**

```text
python
dependency-injection
ioc-container
inversion-of-control
clean-architecture
hexagonal-architecture
fastapi
cqrs
type-hints
asyncio
generics
decorator-pattern
```

Enable **Releases**, **Packages**, and **Discussions**. Keep Issues enabled. Upload `social-preview.png` from this directory as the repository social preview.

## Suggested pinned discussion

**What are you building with Clean IoC?**

Share the kind of application, which features you use, and anything that made adoption harder than it should have been. Small examples are welcome. This thread is also the best place to request an integration or documentation walkthrough before opening a detailed feature issue.

## Beta release after the compiler work

Use the v2.0.0b2 title:

> Compile once, resolve the plan

Lead with the `ContainerBuilder`/immutable `Container` split, strict `build()`, graph-free runtime execution, unified `Component` filters, scope slots, and experimental `ScopeBuilder` overlays. Label the release beta and ask for composition roots that challenge the static model.
