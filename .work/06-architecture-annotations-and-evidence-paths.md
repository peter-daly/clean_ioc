# 06 — Architecture annotations and evidence paths

Status: Planned  
Priority: P1  
Dependencies: 01; 03 for eager/deferred capability summaries  
Related proposal: [Architecture contracts and policy packs](../.v2_roadmap/02-architecture-contracts-and-policy-packs.md)

## Outcome

Attach explicit application documentation to components and show which declared capabilities an entry point reaches,
with evidence paths. Surface existing validation findings directly on graph relationships and mark dependencies the
compiler cannot observe.

```text
ExportOrders
  Declared database capability → OrderRepository
  Declared network capability → ObjectStorageClient
  Declared filesystem capability → CsvWriter
  Unknown additional work → unrestricted Scope resolution
```

Capability summaries report declared composition facts. They do not prove all effects inside arbitrary Python code.

## Current foundation

`Tag`, definition origins, boundaries, compiled paths, custom `ValidationRule` callbacks, and `BuildIssue` already exist.
Tags participate in selection and manifests. Documentation-only annotations should not silently acquire those
semantics. Raw `Scope`/`ResolutionContext` access and arbitrary factories are relevant inspection limitations.

Primary integration points: `metadata.py`, builder registration/decorator/pre-configuration APIs and protocols,
`components.py`, `tooling.py`, `graph_analysis.py`, `bundles.py`, and validation/boundary tests.

## Proposed model and API

- `ComponentAnnotations`: optional owner/team, architectural layer, external-system label, documentation links,
  deprecation information, and explicitly public custom scalar metadata.
- `AnnotationRecord`: subject reference, evidence category `declared`, declaration origin, and safe normalized fields.
- `CapabilityEvidence`: capability, declaring component, consuming root, path, and eager/deferred classification.
- `InspectionLimitation`: path, reason code, and what the compiler does/does not know.
- `ArchitectureReport`: annotations, derived capability reachability, limitations, and linked validation findings.

Start with builder-side `annotate(component_id, ...)` on the shared `ComponentBuilder` protocol. This keeps rich
documentation out of every register signature and applies to stable decorator/pre-configuration IDs where supported.
No annotations are added to application classes automatically.

Proposed methods: `graph.annotations(component)` and `graph.architecture_report(root=None)`.
Existing `Tag("capability", value)` remains the semantic capability declaration mechanism so filters and future policy
packs use one convention. Annotation-only fields do not become selection predicates or semantic fingerprint inputs.

## Implementation stages

### 1. Define declaration storage and ownership

- [ ] Validate annotation keys and bounded values using explicit supported scalar/list/link schemas; reject arbitrary
  Python objects and unbounded nested dictionaries. Treat supplied annotation text as public output.
- [ ] Store annotations in the declaring layer and freeze them into a separate report sidecar at build.
- [ ] Carry annotations to closed specializations with template provenance. Preserve definition versus occurrence-local
  information; do not clone one annotation into conflicting declarations for every occurrence.
- [ ] For overlays, inherited declarations stay immutable. Allow child-local presentation additions only with explicit
  overlay provenance; do not let child documentation rewrite a parent's architectural capability or ownership claim.
- [ ] Validate links as inert HTTP(S) or supported relative documentation paths; render escaped text and never fetch
  or execute a link during compilation. Keep source-code links distinct from user-authored documentation links.

### 2. Propagate capabilities with proof paths

- [ ] Traverse 01 relationships to collect directly declared and transitively reached capabilities per root/boundary.
- [ ] Retain path evidence and distinguish eager reachability from deferred provider/map targets.
- [ ] Deduplicate declarations by component identity but preserve distinct witness paths and boundary crossings.
- [ ] Label absent capability tags as "not declared", not "no external effects".
- [ ] Supply reusable validation helpers for explicitly forbidden capability reachability, integrating with the older
  policy-pack design instead of creating a second independent rule framework.

### 3. Surface graph inspection limitations

- [ ] Mark unrestricted service-locator/context access as possible additional runtime resolution; distinguish declared
  resolution requests already represented by compiled edges from unrestricted operations.
- [ ] Mark arbitrary factory/constructor internals as outside the dependency graph's scope. Keep this concise so every
  ordinary constructor does not produce a warning wall; offer detail on demand and root-level summaries.
- [ ] Do not infer capabilities from module names or AST heuristics by default. Optional user rules may attach claims
  with their own evidence category and provenance.
- [ ] Attach existing BuildIssue findings to exact graph paths when unambiguous, otherwise retain a root-level finding
  with explicit attachment uncertainty. Avoid attaching an issue to an arbitrary same-type occurrence.

### 4. Reports and documentation

- [ ] Add `clean-ioc architecture TARGET [SERVICE] --format text|json|mermaid` with bounded evidence paths.
- [ ] Offer annotation-rich and compact graph projections without changing current default manifest contents.
- [ ] Document capability conventions, team ownership, deprecation notices, and existing custom validation integration.
- [ ] Keep public metadata separate from build-input secrets and state that arbitrary annotation text is not
  automatically sanitized into safe business content.

## Verification

Test declarations on registrations, generic templates, decorators, shared initializers, bundles, and overlays. Cover
capability paths through providers, collections, boundaries, and deferred maps; named registrations with the same
service must retain distinct annotations. Confirm forbidden-capability rules cite an actual reachable path.

Check link escaping/schemes, metadata size/type limits, annotation-only fingerprint stability, and semantic capability
tag changes. Verify unknown runtime resolution is flagged without claiming hidden calls were discovered. Validate
finding attachment for duplicate type names and failures whose paths do not identify one occurrence.

## Acceptance criteria

- Every derived capability includes its declaration and a bounded witness path.
- Declarations, compiled relationships, and inspection limitations are clearly labelled.
- Annotation-only edits do not alter component selection, caches, ownership, or default semantic fingerprints.
- Existing policy callbacks and capability tags remain the single architecture-validation integration point.
