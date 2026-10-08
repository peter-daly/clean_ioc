# Compilation budgets

`CompilationBudget` is an immutable set of optional limits on compiler operation
starts. Pass it through the separate `budget=` keyword on `ContainerBuilder.build()`
or `ScopeBuilder.build()`. A limit accepts an exact built-in non-negative `int`;
`None` means unlimited and `0` refuses the first operation in that unit. Booleans,
integer subclasses, negative values and other types are rejected. Omitting `budget`
creates no allowance state. `CompilationBudget()` enables counting with every
limit unlimited.

```python
from clean_ioc import CompilationBudget, CompilationProfiler, ContainerBuilder

class Leaf:
    pass

builder = ContainerBuilder()
builder.register(Leaf)
profile = CompilationProfiler()
with builder.build(
    budget=CompilationBudget(graph_occurrences=45, active_dependency_depth=3),
    profile=profile,
) as container:
    assert isinstance(container.resolve(Leaf), Leaf)
    assert dict(profile.report().budget_usage)["graph_occurrences"] == 45
```

A single leaf admits 45 physical allocations: 29 component records and 16 provider
target view contexts. Compilation prepares ordinary and managed providers and
provider collections without copying their target subtrees. Its public graph has
one root, and its logical synthetic parent paths reach depth three. Limits use
compiler allocations, rather than public graph visits or retained executable steps.

| Limit | One admitted unit |
| --- | --- |
| `graph_occurrences` | Creation of a component draft, synthetic preview record, or provider target view context. Includes source metadata, visibility/scope-slot records, recursive expansion, and overlay clones. Proven early exclusions create a rejected record only with `diagnostics=True`; ordinary builds charge no occurrence for those excluded definitions. A provider target context counts once regardless of logical subtree size; descendant inspection creates no retained records. Reusing an executable step does not itself count. |
| `active_dependency_depth` | Maximum length of the active component parent path at occurrence creation, including the new component. Roots have depth one. Synthetic providers, collections, clone branches and the complete logical target paths of views count, even though views do not allocate descendant records. Independent roots do not add their depths together. |
| `specialization_materializations` | Start of constructing a new specialized registration after the compiler has established that a cached registration or closed no-op cannot satisfy it. Cache hits do not count. Earlier binding/dependency preparation is a separate preparation operation. |
| `generated_template_outputs` | Start of producing one new registration/decorator template output, before calling its factory. Invalid returns or subsequent failed materialization consume the unit. Already frozen inherited registration-template outputs do not count again. Decorator templates count the outputs they actually regenerate. |
| `diagnostic_attempts` | Start of one recovery compilation for a closed root/boundary root after a failed primary compile. The primary compile is excluded. A failed recovery attempt still consumes its unit. |
| `preparation_operations` | One discovery import attempt; one package-enumeration iterator advance (including terminal advance); one subclass candidate examination, including rejected/abstract candidates; one template source examination; one invoked source/visibility filter or template factory; one uncached specialization preparation; one early eligibility expression evaluation; one invoked registration, candidate eligibility, parent, selection, preference, argument derivation, pre-configuration/decorator applicability, decorator position or provider-map key callback; one entry-point/warm-up selection callback; one build validation rule entry or iterator advance, including the terminal advance. |

These are operation-start counters. An admitted operation consumes allowance even
if it raises. A refused next operation does not run, increment its operation
counter, or produce a success record. A new occurrence and its depth preflight
are admitted together; likewise a new template output and its factory preparation
entry. Depth is a high-water mark, while the other units accumulate across the
whole explicit build.

One allowance covers discovery, registration/decorator expansion, source graph
inspection, boundary preparation, primary compilation and diagnostic recovery.
Recovery never resets it. The mandatory structural-pattern nontermination checks
remain active with any budget. Overlay compilation counts its new inspections,
materializations and clones; it does not charge the caller-owned parent's earlier
build. Runtime resolution, provider invocation, ordinary scope creation and
warm-up activation perform no budget work.

## Exhaustion and diagnostics

```python
from clean_ioc import CompilationBudget, ContainerBuilder, ContainerBuildError

class Leaf:
    pass

builder = ContainerBuilder()
builder.register(Leaf)
try:
    builder.build(budget=CompilationBudget(graph_occurrences=0), diagnostics=True)
except ContainerBuildError as error:
    issue = error.report.errors[0]
    assert issue.code == "compilation-budget-exceeded"
    assert issue.budget.kind == "graph_occurrences"
    assert (issue.budget.maximum, issue.budget.admitted, issue.budget.attempted) == (0, 0, 1)
    assert error.partial_graph.truncated
    assert error.compiled_graph is None
else:
    raise AssertionError("zero occurrences must refuse the first occurrence")

# A new explicit attempt receives a fresh allowance; the failed builder is editable.
with builder.build(budget=CompilationBudget(graph_occurrences=45)) as container:
    assert isinstance(container.resolve(Leaf), Leaf)
```

Exhaustion is an error that warning suppression cannot turn into a valid build.
The immutable `CompilationBudgetExhaustion` sidecar records `kind`, `maximum`,
`admitted`, `attempted`, `phase`, and a snapshot of all admitted units. Path/root
and declaration source evidence are included where the operation has them. Text,
JSON and SARIF include the failure; SARIF also includes the structured sidecar.
With `diagnostics=True`, partial diagnostic graphs and triage show that further evidence was omitted.
Normal builds preserve budget findings and source evidence but do not capture a partial graph.
Recovery operation limits apply in both modes.
Their attempt totals describe actually started compiler views, including preparation
inspections when an allowance is configured; omitted root counts
include roots whose recovery was never started. A truncated graph is evidence
only and cannot execute or create a runtime container.

If recovery runs out of allowance, reports retain the original finding and
already captured findings, add the budget finding and stop recovery. Template
callbacks are never replayed to reconstruct missing evidence. Compiler-owned
validation callback-error messages are sanitized when included in an exhausted
build; explicit user-authored `BuildIssue` messages remain public declarations.
Private build values, owner tokens and callback representations are not budget
metadata.

A `CompilationProfiler` adds optional `budget_usage`/`budget_exhaustion` fields
and a JSON `budget` sidecar. Existing success counters retain their own units;
for example source metadata created outside the primary draft method appears in
the allowance's occurrence count without pretending it was a primary draft.
Profiler detail truncation or clock failures do not affect allowance enforcement.
Budget limits and outcomes do not enter graph fingerprints.

## Matrix variants

```python
from clean_ioc import BuildMatrix, BuildVariant, CompilationBudget, ContainerBuilder

class Leaf:
    pass

def make_builder():
    builder = ContainerBuilder()
    builder.register(Leaf)
    return builder

report = BuildMatrix(
    [
        BuildVariant("standard", make_builder, budget=CompilationBudget(graph_occurrences=45)),
        BuildVariant("restricted", make_builder, budget=CompilationBudget(graph_occurrences=0)),
    ],
    reference="standard",
).check()
assert report.variants[0].is_valid
assert not report.variants[1].is_valid
assert report.variants[1].build_report.errors[0].budget.maximum == 0
```

Each `BuildVariant.budget` applies independently to that variant's fresh build.
There is no matrix-wide allowance, and overlay variants use their existing parent.

## Scope of the limits

A budget is a deterministic work-count limit, not a timeout, memory cap or
sandbox. Arbitrary code inside an admitted callback/import/iterator advance cannot
be interrupted. A single operation can process a large annotation, value,
callback result, package finder result or subclass inventory. Protocol methods
such as hashing/equality and custom reflection are not separately metered.
Snapshot copying, alias validation, inventory scans, graph freezing, indexing and
report rendering have no separate units; occurrence/preparation limits constrain
repeated expansion, but do not bound every byte or instruction in these steps.
Choose the fields matching the work you need to limit. Limits on occurrences
alone permit preparation that does not create occurrences. Registration and
bundle application performed before `build()` are outside its allowance.

Declaring `provider_roots=()` (or selected complete provider annotations) reduces automatic provider preparation.
Any retained private managed-context closure is real compilation work: its records, views, adapter conversions
and graph depth are admitted against the same budgets as public provider forms. The compiler never hides those
allocations or defers their preparation until runtime.
