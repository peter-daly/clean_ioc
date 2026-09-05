# Build-variant matrix checking

Status: Proposal
Priority: P1
Dependencies: Semantic graph-change policy; architecture policy packs

## Summary

Compile an explicit set of named application variants from fresh builders, validate each graph, compare every variant
with a named reference, and enforce cross-variant invariants without serializing build inputs.

## Problem and differentiation

`build_args` allow environment-dependent composition to be frozen safely, but a normal build proves only the selected
configuration. A staging, regional, tenant, or feature combination may contain a missing component, forbidden capability,
or unintended architectural divergence that remains invisible until that variant is built.

Matrix checking applies compiler guarantees across the application's declared composition space. It deliberately avoids
runtime feature-flag behavior and combinatorial guessing.

## Goals

- Build every explicitly supported variant with a fresh single-use builder.
- Aggregate structural and custom validation results by variant.
- Compare valid variants against a named reference using semantic graph changes.
- Enforce common entry-point and maximum-drift invariants.
- Keep build-argument names and values out of all reports and fingerprints.

## Non-goals

- Discovering possible build-argument values automatically.
- Generating a Cartesian product of flags.
- Activating components or testing external services.
- Reusing one builder across variants.
- Supporting arbitrary runtime mutation after a variant has built.

## User stories

- CI proves that production, staging, and local compositions all build.
- A regional deployment may replace a payment adapter but may not lose an entry point or gain a forbidden capability.
- A multi-tenant product checks a representative set of tenant overlays against the base architecture.
- A report shows variant names and semantic drift without revealing environment or tenant inputs.

## Public API

Add `clean_ioc.matrix`:

```python
from clean_ioc.matrix import (
    BuildMatrix,
    BuildVariant,
    MatrixPolicy,
    same_entrypoints,
    semantic_drift,
)
from clean_ioc.tooling import ChangeRisk, DiffPolicy


def make_builder():
    builder = ContainerBuilder()
    configure_application(builder)
    return builder


deployment_matrix = BuildMatrix(
    variants=(
        BuildVariant("production", make_builder, build_args={"environment": "production"}),
        BuildVariant("staging", make_builder, build_args={"environment": "staging"}),
        BuildVariant("local", make_builder, build_args={"environment": "local"}),
    ),
    reference="production",
    policies=(
        same_entrypoints(),
        semantic_drift(DiffPolicy(fail_at=ChangeRisk.high)),
    ),
)

report = deployment_matrix.check()
assert report.is_valid
```

The immutable public records are:

```python
@dataclass(frozen=True, slots=True)
class BuildVariant:
    name: str
    builder_factory: Callable[[], ContainerBuilder | ScopeBuilder]
    build_args: Mapping[str, object] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class BuildMatrix:
    variants: tuple[BuildVariant, ...]
    reference: str
    policies: tuple[MatrixPolicy, ...] = ()

    def check(self) -> MatrixReport: ...


@dataclass(frozen=True, slots=True)
class VariantReport:
    name: str
    build_report: BuildReport
    fingerprint: str | None
    difference: GraphDiff | None


@dataclass(frozen=True, slots=True)
class MatrixReport:
    variants: tuple[VariantReport, ...]
    issues: tuple[BuildIssue, ...]

    @property
    def is_valid(self) -> bool: ...

    def to_text(self) -> str: ...
    def to_json(self, *, indent: int | None = 2) -> str: ...
```

`MatrixPolicy` is a synchronous callback over immutable, redacted variant results. Built-in factories initially provide:

- `same_entrypoints()`: every valid variant exposes the same marked requested types and selected names as the reference;
- `semantic_drift(policy)`: evaluate each valid variant's semantic diff against the reference;
- `require_valid_variants()`: fail when any variant fails to build; included implicitly and cannot be disabled.

Applications may add custom matrix policies, but callbacks receive graph manifests and reports rather than the original
`build_args` mapping.

## Variant execution

Variant names must be unique, non-empty ASCII identifiers containing letters, digits, `_`, `-`, or `.`. The reference
must name one variant.

Variants execute in declaration order. Each factory is called exactly once and must return a mutable, not-yet-built
`ContainerBuilder` or `ScopeBuilder`. The matrix rejects the same builder identity returned for more than one variant.
It calls `build(build_args=...)`, captures the build report and default graph manifest, and closes each successfully built
scope after capture. Closing is safe because builds do not activate user components.

The reference builds in its declaration position rather than being reordered. Diffs are calculated only after all
variants finish. One failing variant does not prevent later variants from building. A failed reference means structural
results are still aggregated, but cross-variant comparison policies produce one `matrix-reference-invalid` issue instead
of cascading errors.

Parallel building is not supported initially. Composition factories may import modules or inspect live Python subclass
sets, so deterministic declaration-order execution is easier to reason about and debug.

## CLI

Add:

```bash
clean-ioc matrix my_app.composition:deployment_matrix
clean-ioc matrix my_app.composition:deployment_matrix --format json
clean-ioc matrix my_app.composition:create_deployment_matrix --format sarif -o matrix.sarif
```

The target is a `BuildMatrix` or a zero-argument factory returning one. It is never a dictionary and the CLI does not
accept build arguments directly. Text, JSON, and SARIF are supported; SARIF follows the architecture-policy mapping and
uses variant names in result properties.

Exit status is `0` when every variant builds and every matrix policy passes, `1` for build or policy findings, and `2`
for invalid matrix definitions, factories, output paths, or locators.

## Reports and serialization

The JSON report has `schema_version: 1` and contains only:

- variant name;
- valid/invalid state and redacted `BuildReport`;
- graph fingerprint for valid variants;
- semantic change kinds, risks, paths, and affected roots relative to the reference;
- matrix-policy findings.

It never serializes `build_args`, including their keys, values, types, count, or hashes. Factory representations,
runtime objects, absolute paths, and configured values are also omitted. Custom matrix policies cannot access build
inputs through the matrix context.

## Invariants and issue codes

- `matrix-invalid-name`: an invalid or duplicate variant name.
- `matrix-reference-missing`: the reference does not name a variant.
- `matrix-factory-error`: a factory raises or returns an unsupported object.
- `matrix-reused-builder`: two variants return the same builder identity.
- `matrix-build-failed`: a variant's build report is invalid; its underlying issues are retained.
- `matrix-reference-invalid`: drift policies cannot evaluate because the reference did not build.
- `matrix-entrypoint-drift`: marked entry points differ from the reference.
- `matrix-graph-drift`: a semantic diff violates the configured `DiffPolicy`.
- `matrix-policy-error`: a custom policy raises, returns a non-iterable, or yields malformed issues.

Policy exceptions do not stop subsequent policies. Issue ordering is variant declaration order, build issue order, then
matrix policy order.

## Overlay handling

A variant factory may return a `ScopeBuilder` anchored to a parent scope created inside that factory. The factory owns
that setup and must keep the parent open until the matrix closes the built overlay. For simpler ownership and reliable
cleanup, the recommended form is a root `ContainerBuilder` with environment choices expressed through `build_args`.

Matrix checking does not manufacture overlays or copy builders. Parent singleton anchoring and overlay validation use the
normal compiler rules.

## Compatibility

This is an additive tooling module and command. Normal `build()`, `check`, `graph`, and `diff` are unchanged. A matrix
uses public builder factories specifically because successful builders are single-use.

## Rejected alternatives

- **Pass build inputs on the CLI:** shell history and CI logs are poor places for secrets and environment structure.
- **Reuse a frozen blueprint automatically:** builder factories may intentionally compose different modules.
- **Generate all flag combinations:** only explicitly supported variants have a meaningful product contract.
- **Stop after the first failure:** aggregated failures are the main value of matrix checking.
- **Build variants concurrently:** import state and subclass discovery make deterministic sequential behavior safer.

## Rollout

1. Add sequential variant building, aggregate reports, and strict redaction tests.
2. Add same-entrypoint comparison and semantic drift policies.
3. Add text/JSON CLI output.
4. Add provenance-backed SARIF output and documented CI examples.

## Acceptance tests

- Build multiple root and overlay variants from fresh factories in declaration order.
- Reject duplicate/invalid names, missing references, reused builders, built runtimes, and invalid factory results.
- Continue after factory and build failures while preserving underlying issue paths.
- Compare valid variants with the reference and enforce entry-point and semantic-drift policies.
- Handle an invalid reference without cascading one issue per unavailable diff.
- Run all custom policies after a policy error and validate yielded issue types.
- Close every successfully built scope on success and failure paths without activating components.
- Verify text, JSON, SARIF, output-file, locator, and exit-status behavior.
- Search every serialized form to prove build-argument keys, values, types, counts, hashes, and absolute paths are absent.
