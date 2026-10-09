# 06 — Artifact format, compatibility and packaging

Created: 2026-10-09\
Status: Not ready — artifact and compatibility contracts need decisions\
Assignment: Unassigned\
Prerequisites: Contracts/findings from 01–05; reporting requirements from 08

## Outcome

Define and implement an explicit executable artifact format and a build/export/
load workflow that works from an installed application. Keep shared execution
structure compact and reject incompatible or incomplete artifacts clearly.

## Readiness and remaining decisions

- Choose the public programmatic entry points and whether an initial CLI is
  required. Decide how an export obtains its frozen plan without activating the
  application and how optional reporting payloads are selected.
- Review exact-application/image coupling as the first compatibility policy.
  Specify Python implementation/version, Clean IoC, application and dependency
  identities, target platform, and supported feature requirements.
- Choose the artifact record/envelope design and freshness/integrity mechanism.
  Separate executable compatibility from public unversioned analysis manifests.
- Decide how packaging identifies installed distributions/modules without a
  repository checkout or `uv.lock` at runtime.
- Resolve the representations for slots, symbols, constants, owner relationships
  and optional profiling metadata with their owning tasks.

Recommended first scope: trusted build outputs packaged with the exact target
application image, regenerated on incompatible changes. Cross-platform loading,
long-term migration adapters and loading untrusted arbitrary artifacts are not
proposed for the first delivery. These are review choices, not existing guarantees.

## Work

1. Define explicit records for executable steps, roots, dependencies, type/callable
   references, slot bindings and logical ownership. Keep compiler-only information
   out unless an enabled optional capability requires it.
2. Replace implicit dependence on private dataclass/slot field order with a
   deliberate encoding contract. Preserve shared references and define supported
   cycles or reject them before completing export. Avoid CPython object-layout
   introspection as an undocumented format requirement.
3. Define envelope compatibility checks and reference/semantic validation.
   Verify what can be checked before Python imports, then validate imported
   symbols and reconstructed records before activation. Referenced modules can
   execute import code; an integrity check does not make them safe to execute.
4. Provide atomic export and explicit load operations that work in a fresh
   installed application. Report which compatibility input or required feature
   differs. A load failure must not silently fall back to graph compilation.
5. Document a target-image build stage and runtime packaging example. Code and
   dependencies required by symbols remain installed. Do not assume an artifact
   compiled on local ARM is equivalent to one built for production x86.
6. Distinguish byte integrity, semantic equivalence and freshness. Random/internal
   IDs must not be mistaken for application-defined stable bindings; the public
   structural fingerprint is not a complete fingerprint of executable values.
7. Preserve the existing private experiment and its measurements as evidence.
   Define how it relates to the supported path without silently presenting its
   current schema as a production API or changing public report formats.

## Verification and acceptance

- [ ] The format and compatibility policy are documented, including unsupported
  features, code dependencies and artifact regeneration rules.
- [ ] Independent compile/export/load processes work from an installed package
  without access to this repository layout or its lockfile.
- [ ] Tests reject truncated/corrupt data, invalid references/records, missing
  symbols and incompatible code/runtime/feature combinations before activation.
- [ ] Atomic export leaves an existing valid artifact intact on failure.
- [ ] Shared steps and logical ownership survive loading, while task 04's mutable
  state is freshly created and task 05's value policy is enforced.
- [ ] Loading performs no graph compilation, and its retained/peak memory is
  measured against the existing reduced-artifact baseline.

## Starting points

- `_FIELDS`, `_Writer`, `_Reader`, `_compatibility`, `dump_graph` and `load_graph`
  in the [experimental codec](../../benchmarks/graph_artifact.py).
- [Experiment documentation](../../docs/graph-artifact-experiment.md),
  [artifact tests](../../tests/test_graph_artifact_experiment.py) and
  [packaging configuration](../../pyproject.toml).
- [Post-task-05 measurements](../graph-memory-optimization/artifact-retest-post05.md).
