---
description: Inspect, validate, render, and diff Clean IoC's compiled dependency graph in Python or CI.
---

# Compiler tooling

Clean IoC can treat an application's dependency graph as a build artifact. Mark the public requests that start your application, build once, and then inspect the exact component plans that runtime resolution will execute.

```python
from clean_ioc import ContainerBuilder

builder = ContainerBuilder()
builder.register(PaymentGateway, StripeGateway)
builder.register(Checkout)
builder.mark_entrypoint(Checkout)

container = builder.build()
print(container.build_report.to_text())
print(container.graph.to_text())
```

An entry point changes the default tooling view, not compilation or resolution. Clean IoC still compiles and validates every visible root, and an unmarked root remains resolvable. Once any entry point is marked, registrations outside all marked component trees produce `unreachable-component` warnings.

Mark a collection when every implementation is an application entry point:

```python
builder.mark_entrypoint(list[MessageHandler])
```

## Structured build reports

A successful runtime exposes its immutable `BuildReport` as `container.build_report`. A failed build raises `ContainerBuildError` with the same report on `error.report`.

```python
from clean_ioc import ContainerBuildError

try:
    container = builder.build()
except ContainerBuildError as error:
    for issue in error.report.errors:
        print(issue.code, issue.path, issue.message)
```

Independent root failures are aggregated so one build can report several composition mistakes. Issues have a stable code, `error` or `warning` severity, a message, and a semantic component path. Errors always fail the build; warnings are available for policy in tooling and CI.

Current issue codes include:

- `missing-component`, `missing-entrypoint`, and `ambiguous-selection`;
- `circular-dependency` and `captive-dependency`;
- `generic-specialization` and `overlay-singleton`;
- `unreachable-component`.

## Render the compiled graph

The graph includes registrations plus the activation edges that are easy to miss in a registry dump: decorators, pre-configurations, default and configured values, runtime contexts, value providers, and declared scope slots.

```python
text = container.graph.to_text()
mermaid = container.graph.to_mermaid()
manifest = container.graph.manifest()

print(manifest.fingerprint)
```

Renderers and manifests show marked entry points by default. Pass `all_roots=True` to inspect every compiled root.

The JSON manifest is deterministic across equivalent builds. It uses semantic paths and qualified type names instead of component UUIDs or memory addresses. Fixed values are represented by type and activation kind; their contents are not serialized. This makes manifests suitable for review without leaking configured secrets.

```python
from clean_ioc import GraphManifest

baseline = GraphManifest.from_json(saved_json)
difference = container.graph.manifest().diff(baseline)

for change in difference.changed:
    print(change.path)
```

Manifest schema version `1` is validated when loading. A diff reports added, removed, and semantically changed component paths.

## Use it from the command line

Expose a builder, built scope, or zero-argument composition factory from an importable module:

```python
# my_app/composition.py
def application_builder():
    builder = ContainerBuilder()
    builder.register(PaymentGateway, StripeGateway)
    builder.register(Checkout)
    builder.mark_entrypoint(Checkout)
    return builder
```

Then validate, render, and diff it without starting the application:

```bash
clean-ioc check my_app.composition:application_builder
clean-ioc graph my_app.composition:application_builder --format mermaid
clean-ioc graph my_app.composition:application_builder --format json -o dependency-graph.json
clean-ioc diff my_app.composition:application_builder dependency-graph.json
```

`check` exits non-zero for build errors. Warnings are informational by default; `--strict` makes unsuppressed warnings fail, and `--ignore CODE` suppresses a warning code. Errors cannot be ignored.

`diff` exits `0` when the graph is unchanged and `1` when it changed. Add `--all` to `graph` or `diff` when the baseline should include every root rather than the entry-point view. Baselines are never updated implicitly.

One minimal CI policy is:

```yaml
- name: Validate dependency graph
  run: clean-ioc check my_app.composition:application_builder --strict
- name: Detect dependency graph changes
  run: clean-ioc diff my_app.composition:application_builder dependency-graph.json
```

Update the checked-in manifest deliberately when a reviewed composition change is expected.
