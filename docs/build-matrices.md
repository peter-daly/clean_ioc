---
description: Build and validate every supported composition, then compare variants against a named reference.
---

# Build-variant matrices

A `BuildMatrix` checks an explicit list of supported environments, tenants, or feature configurations. Each variant
gets a fresh builder, runs ordinary build and validation rules, and is compared with a named reference. One failing
variant does not stop the remaining variants. The matrix produces one report for unit tests or CI without activating
application components.

## Declare supported variants

This complete example checks production, staging, and local compositions. Production selects the real repository;
the other environments select a sandbox implementation. All variants must expose the same entry points, and only
the expected repository implementation change is permitted:

```python
from clean_ioc import ContainerBuilder
from clean_ioc.matrix import BuildMatrix, BuildVariant, same_entrypoints, semantic_drift
from clean_ioc.tooling import ChangeAllowance, ChangeRisk, DiffPolicy, GraphChangeKind


class Repository:
    pass


class SqlRepository(Repository):
    pass


class SandboxRepository(Repository):
    pass


class Application:
    def __init__(self, repository: Repository):
        self.repository = repository


def make_builder():
    builder = ContainerBuilder()
    builder.register(
        Repository,
        SqlRepository,
        when=lambda component: component.build_args["environment"] == "production",
    )
    builder.register(
        Repository,
        SandboxRepository,
        when=lambda component: component.build_args["environment"] != "production",
    )
    builder.register(Application, root_policy="entrypoint")
    return builder


deployment_matrix = BuildMatrix(
    variants=[
        BuildVariant("production", make_builder, build_args={"environment": "production"}),
        BuildVariant("staging", make_builder, build_args={"environment": "staging"}),
        BuildVariant("local", make_builder, build_args={"environment": "local"}),
    ],
    reference="production",
    policies=[
        same_entrypoints(),
        semantic_drift(
            DiffPolicy(
                fail_at=ChangeRisk.medium,
                deny_kinds=frozenset({GraphChangeKind.lifespan_changed}),
                allowances=(
                    ChangeAllowance(
                        kind=GraphChangeKind.implementation_changed,
                        path_glob="*/dependency:repository:*",
                        maximum_risk=ChangeRisk.high,
                    ),
                ),
            )
        ),
    ],
)

report = deployment_matrix.check()
report.assert_valid()
assert len(report.variants) == 3
assert report.variants[1].difference.semantic_changes
```

Variant names are public report labels. Names must be unique, non-empty strings containing only ASCII letters, digits,
`_`, `-`, or `.`. The reference must name one declared variant. Variant and policy lists are captured at construction;
each variant also captures its input mapping, excluding it and its factory from the record's representation.

Factories are synchronous, zero-argument callables returning an unbuilt `ContainerBuilder` or `ScopeBuilder`. Every
factory is called exactly once per check, in declaration order, including the reference at its declared position.
A builder returned by two factories is rejected even if its first build failed. A subsequent `check()` calls the
factories again, so reusable matrix definitions require factories that return fresh builders every time.

The matrix lists supported combinations explicitly. It does not infer input values, generate flag combinations, run
components, or test external services.

## Validation and comparison policies

Each build runs the normal compiler and build-mode validation rules. After a successful build, the matrix runs the
validation-only rules once and retains the earlier build findings without rerunning build rules. Every successfully
built scope is closed after its report and graph snapshots are captured, including when validation fails.

| Policy | Meaning |
| --- | --- |
| `require_valid_variants()` | Every variant must pass compilation and validation. Always enforced, including when no policies are declared. |
| `same_entrypoints()` | Valid variants must expose the same marked requested types and selected names as the reference. Collection requests and duplicate unnamed selections are retained. |
| `semantic_drift(DiffPolicy(...))` | Apply a graph-change policy to every valid variant's classified changes from the reference. |

Comparisons use the default graph view, focused on marked entry points when any exist. A valid reference has an empty
self-diff. Invalid variants have no fingerprint or diff. If the reference fails, valid variants still retain their
fingerprints, but all comparisons are unavailable and one `matrix-reference-invalid` finding is emitted. Built-in
comparison policies skip unavailable comparisons, and custom policies still run.

`VariantReport.is_valid` describes that variant's compilation and validation results. `MatrixReport.is_valid` also
checks cross-variant findings. Warnings alone pass, consistently with the Python validation report API.
Policy failures do not stop later policies. A generator's valid findings are retained if it subsequently fails.

See [Graph-change policies](graph-change-policies.md) for classification, risk thresholds, denied kinds, and allowance
precedence. Matrix policies use those same acceptance rules.

## Custom matrix policies

`MatrixPolicy` is a synchronous callback receiving a frozen `MatrixContext` and returning an iterable of `BuildIssue`
records. The context exposes the reference name, `reference_report`, and redacted `VariantReport` records. Use
`context.manifest(name)` for a detached `GraphManifest` snapshot, or `None` when the variant is invalid.
`context.issue(name, code, message, ...)` associates a finding with one declared variant:

```python
from clean_ioc import ContainerBuilder
from clean_ioc.matrix import BuildMatrix, BuildVariant, MatrixContext


class Worker:
    pass


def make_builder():
    builder = ContainerBuilder()
    builder.register(Worker, root_policy="entrypoint")
    return builder


def require_entrypoints(context: MatrixContext):
    for variant in context.variants:
        if variant.is_valid and not variant.entrypoints:
            yield context.issue(
                variant.name,
                "application-entrypoints-required",
                "Every supported composition must declare an application entry point.",
            )


matrix = BuildMatrix(
    [BuildVariant("production", make_builder), BuildVariant("staging", make_builder)],
    reference="production",
    policies=[require_entrypoints],
)
matrix.check().assert_valid()
```

Callbacks receive no builders, containers, components, or original build inputs. Their build reports have no private
live graph context. Each callback receives detached diff dictionaries and manifest snapshots; modifying a retrieved
snapshot cannot change subsequent policies or the final report. Async callbacks, non-iterable results, malformed
findings, and callback exceptions produce `matrix-policy-error` findings. Exception messages and callable
representations are not copied into reports. Custom finding messages are application-authored report content.

For a finding tied to a graph occurrence, pass its manifest path as `path=(manifest_path,)`. Matrix SARIF can use the
captured registration source for that path. Removed occurrences use the reference's source when available.

## Reports and assertions

The report includes variant names, each redacted build report, valid graph fingerprints, classified differences, marked
entry-point identities, and matrix findings. `to_dict()`, `to_json()`, and `to_text()` preserve declaration order.
Underlying build issues retain their original codes and component paths. Matrix findings follow implicit validity
findings, the unavailable-reference finding when applicable, and explicit policies in declaration order.

Use `report.assert_valid()` in a unit test. A valid report returns normally. An invalid report raises `AssertionError`
containing a SARIF document with variant labels and available source links. Warnings alone pass. The assertion remains
active under optimized Python because it uses an explicit exception.

`report.to_sarif()` emits SARIF 2.1.0 with one run per variant, plus a run for matrix-policy findings when present.
Results tied to a variant include `properties.variant`; runs also identify the reference. Build findings retain
registration locations and dependency code flows. Graph-drift findings include available current or reference sources.
Rendering captured reports does not rebuild or revalidate variants. Export SARIF through the matrix report to include
its captured source information.

Build inputs are not exported as keys, values, input-type metadata, counts, or input hashes. Matrix snapshots replace
supplied value nodes' actual Python types with their declared dependency types before comparing or fingerprinting.
Declared application types and architectural changes remain visible. Matrix fingerprints describe this redacted default
view; ordinary graph manifests and their fingerprints are unchanged. Reports also omit runtime identities and absolute
source paths. JSON remains unversioned during beta; SARIF uses the required standard version.

## CLI

Point the command at a `BuildMatrix` object or a zero-argument factory returning one:

```console
clean-ioc matrix my_app.composition:deployment_matrix
clean-ioc matrix my_app.composition:make_deployment_matrix --format json -o matrix.json
clean-ioc matrix my_app.composition:deployment_matrix --format sarif -o matrix.sarif
```

The CLI does not interpret dictionaries as matrices or accept build inputs on the command line. Inputs belong in the
declared variants. Factory errors still produce aggregated reports, with later variants checked before the command
returns. Invalid target definitions and locators leave existing output files untouched.

| Exit status | Meaning |
| --- | --- |
| `0` | Every variant passes and no matrix policy reports an error. |
| `1` | A compilation, validation, cleanup, or matrix-policy finding fails the check. |
| `2` | Invalid definitions, factories, reused builders, locators, or output paths. |

Matrix checks can run directly in CI and save a text, JSON, or SARIF artifact. Workflow checkout and artifact-upload
configuration can be added separately.

## Scope ownership

A factory may return a fresh `ScopeBuilder` anchored to an open parent scope. The matrix closes the built overlay;
the factory's caller owns the parent and must keep it open throughout the check. Parent singleton anchoring and overlay
validation follow the ordinary compiler rules. The matrix does not copy builders, manufacture overlays, or close
caller-owned parents. A root `ContainerBuilder` with choices expressed through `build_args` is usually simpler.

Current matrix issue codes include `matrix-invalid-name`, `matrix-reference-missing`, `matrix-invalid-variant`,
`matrix-invalid-inputs`, `matrix-factory-error`, `matrix-reused-builder`, `matrix-build-failed`,
`matrix-reference-invalid`, `matrix-entrypoint-drift`, `matrix-graph-drift`, and `matrix-policy-error`.
