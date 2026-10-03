# 05 — Failed-build diagnostic graphs

Status: Implemented and independently reviewed (2026-09-12)  
Priority: P1  
Dependencies: 01 reference conventions; 04 is an optional detail enhancement

## Outcome

Attach a partial, non-executable graph to a failed build so developers can see the failing edge, relevant ancestor
path, examined candidates, and successfully compiled branches. Preserve incomplete knowledge explicitly.

```text
PlaceOrder
└─ repository: OrderRepository
   └─ connection: Connection
      └─ ✕ missing registration

ReportCache [singleton]
└─ builder: ReportBuilder [transient]
   └─ request: RequestContext [scope slot]
      └─ ✕ retained by ReportCache
```

## Current foundation

`ContainerBuildError` carries `BuildReport` and partial `CompilationExplanation` records. `_Compiler` has mutable
component drafts while descending. `_compile_with_report()` catches failures; `_error_report()` recompiles independent
roots to aggregate findings. A failed draft graph cannot safely be exposed as a valid `CompiledGraph` or `_PlanSet`.

Primary integration points: `ContainerBuildError`, `_Compiler` descent and `_draft()`, `_error_report()`,
`_compile_with_report()`, `components.py`, `tooling.py`, `cli.py`, and build-error tests.

## Proposed model and API

Add separate frozen `PartialGraph`, `PartialNode`, `PartialEdge`, and `CompilationAttempt` records.

- Node/edge states: complete, failed, rejected, and not-examined. "Complete" means structural compilation completed,
  not that activation succeeded or that final custom validation approved the graph.
- Failure records carry stable issue codes, safe structural labels, witness paths, and links to candidate decisions.
- Cycles are represented as explicit back-reference edges, not recursive object structures.
- Attempt/root identity keeps diagnostic retries distinct. Unknown/unvisited work must not be fabricated as missing.

Proposed API: `error.partial_graph`, with `to_text()`, `to_json()`, and `to_mermaid()`.
Add `clean-ioc graph TARGET --on-error partial --format text|json|mermaid`; retain exit code 1 for failed builds even
when a diagnostic artifact was successfully written. Default CLI behaviour remains unchanged.

## Implementation stages

### 1. Define safe partial snapshots

- [x] Create diagnostic records independent of normal frozen component records; tolerate absent implementation,
  ownership, generic mapping, or dependency fields when compilation never established them.
- [x] Snapshot safe graph drafts and issue context when an attempt fails. Never run normal graph-freeze operations
  that require successfully resolved types or complete relationships just to render a failure.
- [x] Explicitly represent failures before graph allocation, such as invalid aliases or boundary contracts, as
  declaration/attempt failures without inventing component nodes.
- [x] Ensure snapshots do not retain execution contexts, traceback frames, runtime scopes, or configured values.

### 2. Capture failure relationships

- [x] Record parameter edges before descent so a missing registration has a real diagnostic attachment point.
- [x] Capture cycle target, retaining ancestor for captive dependencies, generic request/template context, and invalid
  decorator/pre-configuration linkage with precise safe paths.
- [x] Capture rejected candidates only after their predicates were actually evaluated. A candidate failing structural
  compilation before its `when` runs must be labelled failed, not rejected by that predicate.
- [x] Do not continue normal compilation with placeholder executable steps. Diagnostic placeholders never enter a
  `Container`, `_RootPlan`, or successful runtime cache.

### 3. Aggregate root attempts honestly

- [x] Extend `_error_report()` to collect each retry's partial result alongside its finding, without adding extra
  retry passes merely for display.
- [x] Keep attempts separate when callbacks yield inconsistent retry outcomes; do not merge their nodes into one
  supposedly coherent successful graph. Include an attempt inconsistency indicator if needed.
- [x] Deduplicate equivalent structural failures with deterministic keys while retaining affected root references.
- [x] Set maximum captured nodes/candidates/paths and explicit truncation markers to prevent failure reporting from
  exhausting memory on a large invalid composition.
- [x] Preserve builder repairability: a later successful build produces a fresh graph with no stale failure state.

### 4. Render and expose

- [x] Render completed branches normally, failures with issue markers, rejected alternatives separately, and known but
  unexamined alternatives as not-examined.
  branches as not examined. Always title the artifact "Partial diagnostic graph — build failed".
- [x] Add issue-to-node links in JSON and safe Mermaid labels with escaping for user-controlled type/tag strings.
- [x] Keep these artifacts out of successful graph manifests, semantic diffs, and executable-plan loaders.
- [x] For custom-rule failures after compilation, expose a structurally complete diagnostic graph with failed
  validation findings; do not describe the runtime as successfully built.

## Verification

Exercise missing dependency, cycle, transitive captive dependency, missing slot, conflicting generic binding,
non-terminating pattern expansion, invalid decorator, initializer cycle, boundary failure, and alias failure before
node creation. Include several independent failing roots and a rule failure after structural compilation.

Verify retry attempt separation, truncation, deterministic serialization, escaped Mermaid syntax, and successful repair
of the same builder. Place secrets in exception messages and derivation inputs: diagnostic labels should use sanitized
structural messages and codes, not blindly serialize exception text. Existing BuildReport compatibility is preserved;
new partial-graph output must not introduce additional secret exposure.

## Acceptance criteria

- Every supported structural failure has a useful safe partial artifact or an explicit pre-graph failure record.
- Rejected, missing, failed, and not-examined are never conflated.
- Failed plans remain non-executable, failed-build exit codes remain failures, and retry outcomes remain distinguishable.
- Diagnostic generation does not invoke extra user activation or add extra composition passes.
