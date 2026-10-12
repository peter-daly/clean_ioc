# Build and analysis boundaries

`ContainerBuilder.build()` discovers registrations, binds dependencies and emits execution instructions. It runs no
built-in policy audit or custom validation rules. Impossible binding, such as a missing required dependency or a cycle,
still raises a local `ContainerBuildError`. Actual runtime ownership, async, scope and cleanup guards remain enforced.
Compilation does not activate constructors, resource factories or application context managers. Explicit composition
callbacks, including filters, templates and `derive(...)`, can run while wiring the plan.

`ContainerBuilder.verify()` runs the complete available validation workflow and returns a `VerificationReport`.
`result` is a completed `VerificationReport` with findings, root coverage, stage outcomes, rule outcomes and
`complete`. It is invalid if it contains errors or the analysis is incomplete. A policy failure can coexist with an
emitted test plan. A binding failure can leave a partial diagnostic graph and no executable plan.

```python
with application_builder().verify() as result:
    result.assert_valid()
    with result.create_runtime() as runtime:
        runtime.resolve(Application)
```

`create_runtime()` uses the emitted plan without recompilation. Each test runtime gets independent singleton and
pre-configuration state, except real parent anchors borrowed by an overlay. Closing the result closes owned test
runtimes in reverse order. It never closes a borrowed parent or a composition handle. Production separately uses
`application_builder().build()` with the same intended inputs.

## Custom graph rules

Register every rule with `add_validation_rule(rule)`. There is no mode or phase. A synchronous rule receives a
`ValidationContext` and returns or yields `BuildIssue` values. `context.graph.walk()` visits full occurrence paths,
including providers, decorators, pre-configurations and boundary roots. `visit.issue(...)` supplies exact provenance.
`context.type_ast(type)` lazily parses available source once per type in the analysis context.

```python
def require_owner(context):
    for visit in context.graph.walk():
        if not any(tag.name == "owner" for tag in visit.component.tags):
            yield visit.issue("application-owner", "Every component needs an owner tag")

builder.add_validation_rule(require_owner)
result = builder.verify()
print(result.to_text())
```

Every available rule completes once before `verify()` returns. Rule errors become `validation-rule-error` findings;
prior yielded findings remain and later rules continue. Missing full graphs, cancellation and budgets produce explicit
unavailable or interrupted outcomes. Report and graph reads never rerun rules. See the
[custom validation cookbook](custom-validation.md) for policy examples and [tooling](compiler-tooling.md) for CLI usage.

## Findings and attempts

Verification checks captive lifespans, decorator and argument policies, factory return annotations, reachability and custom
application rules. `result.graph` holds full inspection when available; `result.partial_graph` contains bounded,
non-executable evidence after a binding failure. `result.selection_census()` and `result.triage_report()` read captured
facts. Independent diagnostic root attempts may repeat wiring callbacks and retain inconsistency evidence, but never
rerun validation declarations. Production build has no such retries or rich error report.

Every admitted build or verification attempt consumes its builder, whether it succeeds, fails, is cancelled or exhausts a
budget. Correct the composition factory and obtain a fresh builder to retry. Invalid arguments rejected before
admission leave the builder editable. Do not catch a failure and mutate the consumed builder.

## CI and scopes

Use `clean-ioc check my_app.composition:application_builder` for one complete analysis. Errors and incomplete analysis
fail; strict mode also fails on unsuppressed warnings. One configuration's analysis does not approve different future
build inputs. Keep separate CI coverage for each supported composition variant.

Ordinary `new_scope()` reuses execution and runs no analysis. For different registrations, retain external composition
before building and pass it to `ScopeBuilder(parent, composition=handle)`. Verification captures a handle automatically.
The child can build execution or verify its own graph; inherited rules run only in the latter operation.
