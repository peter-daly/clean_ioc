# GitHub repository profile

Apply these settings in **GitHub → About → Edit repository details** after the local changes are published.

## About

**Description**

> Typed Python dependency injection that validates and explains object graphs before startup. Explicit lifespans, async cleanup, generics, decorators, and FastAPI request scopes.

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

## First release after the repositioning

Use the v1.25.0 title:

> Prove your dependency graph before startup

Lead the release notes with `validate()` and `explain()`, then concurrency/lifetime safety, broad FastAPI compatibility, and the runnable example. The release workflow now creates a GitHub Release with generated notes and built artifacts.
