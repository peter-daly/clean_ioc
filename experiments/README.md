# Sealed container compiler experiment

This private prototype tests one question: can Clean IoC move dependency-plan
discovery from every resolution into an explicit `seal()` phase without changing
the public container yet?

It is deliberately outside `clean_ioc/`, so Hatch does not publish it. The root
container remains mutable until `seal()`, then validates and compiles the default
sync and async resolution paths. Unsupported features use the existing resolver.
User factories are never retried after activation starts.

## Child scopes

`expect_to_be_scoped()` declares a slot that a child scope may fill after the root
is sealed. Those registrations are looked up dynamically inside the otherwise
compiled plan. The experimental FastAPI adapter declares the four request-local
types supplied by the existing extension:

```python
from experiments.compiled_container import CompiledContainer
from experiments.compiled_fastapi import prepare_fastapi_scope_slots

container = prepare_fastapi_scope_slots(CompiledContainer())
container.register(MyHandler)
container.seal()
```

An undeclared child registration, patch, decorator, or pre-configuration makes
that child use Clean IoC's existing resolver. A child never mutates the sealed
root plan.

## Known fallback boundaries

The prototype currently falls back for custom value providers, `CurrentGraph`,
open-generic fallback, filtered or modified collections, custom dependency or
node filters, custom decorator/pre-configuration filters, and collections that
contain scope slots. `CompilationReport.fallbacks` makes those decisions visible.

This is an experiment, not a supported API. It uses Clean IoC internals and is
expected to change or be deleted.

## BenchBro experiment

The comparison prepares containers outside the measured interval, compares the
same five-node graph on the existing and compiled resolvers, exercises a declared
request-scope slot, and measures `seal()` separately:

```bash
uv run benchbro list --config experiments/benchbro.toml --verbose
uv run benchbro run --config experiments/benchbro.toml --no-compare
```

Repeat the unchanged run before interpreting it. Inspect sample count, confidence
margin, CV, and outliers rather than treating a single timing as a promise. Output
is written below `.benchbro/compiled-container/`, which remains machine-local and
ignored by Git.

### Local directional snapshot

On 28 August 2026, CPython 3.14.4 on macOS arm64 produced this higher-sample run:

| Operation | Existing median | Compiled median | Direction |
| --- | ---: | ---: | ---: |
| Five-node graph | 44.00 µs | 33.45 µs | 24.0% lower median latency |
| Request-scope slot graph | 64.09 µs | 44.99 µs | 29.8% lower median latency |
| Build and seal five-node container | — | 458.59 µs | startup cost |

The resolution medians moved in the same direction across four runs. The final
run used 15–24 repeat samples with CVs of 4.0–7.3% and relative 95% margins of
2.1–3.3%. BenchBro marked every row noisy because each contained IQR outliers.
Treat the result as evidence worth pursuing, not as a stable performance claim or
release threshold.
