# Contributing to Clean IoC

Thanks for helping improve Clean IoC. Focused bug reports, small reproducible examples, documentation corrections, and well-tested changes are all welcome.

## Set up the project

Clean IoC uses [uv](https://docs.astral.sh/uv/) for its development environment:

```bash
git clone https://github.com/peter-daly/clean_ioc.git
cd clean_ioc
uv sync --all-groups
```

Run the complete local check:

```bash
make ci
```

This runs linting, formatting checks, type checks, tests, and documentation-example validation.

## Propose a change

1. Open an issue first when behavior or public API will change materially.
2. Add a regression test or an example that demonstrates the desired behavior.
3. Keep application-facing APIs typed and avoid requiring application classes to depend on Clean IoC.
4. Update the README or relevant guide when users need to make a decision differently.
5. Add a changelog entry for user-visible behavior.

## Test focused areas

```bash
# Core suite
uv run pytest -q tests

# FastAPI integration
uv run pytest -q tests/ext/fast_api

# Runnable example
uv run pytest -q examples/fastapi_clean_architecture

# Documentation site
uv run mkdocs build --strict
```

When changing performance-sensitive graph construction, run the reproducible microbenchmarks before and after on the same machine:

```bash
uv run python benchmarks/benchmark.py
```

## Design principles

- Keep domain and application objects unaware of the container.
- Prefer explicit registration at a composition root over hidden global lookup.
- Treat lifespans as ownership rules, not performance switches.
- Preserve sync and async cleanup semantics.
- Make invalid configuration fail with an actionable dependency path.
- Avoid breaking public behavior without a clear migration path.

By participating, you agree to keep discussion constructive, specific, and respectful.
