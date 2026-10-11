# Run and analysis contract

Decision date: 2026-10-10. Task 10, approved by the coordinating maintainer agent.
The immediate RC migration replaces public build switches, without an adapter.

## Public API and inputs

`ContainerBuilder.build(mode="run")` and `ScopeBuilder.build(mode="run")` are
the defaults. The only other value is `"analysis"`; `BuildMode` names their
literal type. Invalid modes and removed keywords fail before compilation or
profiling and do not consume the builder. `Scope.build_mode` reports the mode.

| Former build parameter | Replacement / run | Analysis |
| --- | --- | --- |
| `diagnostics` | Removed; no retained diagnostic history | Complete captured diagnostic history |
| `explain_metadata` | Removed; retain executable relationships and discovery only | Complete supported inspection evidence |
| `check_unreachable` | Removed; no optional reachability advisory pass | Check reachability during build |
| `aggregate_errors` | Removed; preserve original failure without independent root retries | Aggregate independent failed roots using existing retry safeguards |
| `clean_orphans` | Removed; skip unused dependency-only graphs and release orphan composition | Compile/validate unused dependency-only declarations without public-root expansion |
| `allow_scope_builders` | Removed; release blueprint, reject overlays | Retain blueprint and permit overlays |
| `provider_roots` | `builder.set_provider_roots(annotations)` declaration | Identical declaration semantics |
| `build_args` | Unchanged immutable composition input | Same |
| `budget` | Unchanged compilation resource limit | Same; additional analysis work consumes its applicable budgets |
| `profile` | Unchanged compilation observer | Same |
| `instrumentation` | Unchanged runtime observer; temporary captured attribution evidence allowed | Same; activity still requires actual resolution |

`set_provider_roots(None)` selects the automatic provider surface (the default).
An empty iterable selects no automatic handles. A nonempty iterable selects those
canonical provider annotations, plus explicitly marked provider entrypoints.
Injection and private managed acquisition targets are unaffected. Input is captured
at declaration time; repeated calls replace the declaration, and invalid calls
leave the previous declaration intact. Scope builders start with the same `None`
default as the old build parameter; they do not silently inherit a parent's
restricted public surface. Setting the declaration requires a mutable builder.

## Runtime capability matrix

| Capability | Run | Analysis |
| --- | --- | --- |
| Resolve, async resolve, providers/maps, filters | Supported | Supported |
| Scope slots, ordinary child scopes, identity and cleanup | Supported | Supported |
| `components` and their executable parent/dependency/decorator relationships | Supported | Supported |
| `selected_registrations`, including selected dependency-only/deferred targets | Complete existing discovery semantics | Same |
| Warmup declarations and explicit warmup execution | Supported | Supported |
| Runtime profiling and compilation profiling | Supported | Supported |
| `build_args`, import inventory, `build_report` | Supported; report contains mandatory/build-rule findings | Supported, including unreachable advisories |
| `graph`, graph walk, explanations, manifests, census, ownership/analysis reports | Clear unavailable-capability error | Supported |
| `validation_report()` | Clear unavailable-capability error | Explicit full-validation workflow |
| New scope builder / direct `ScopeBuilder(parent)` | Rejected | Supported |
| Ordinary scopes | Inherit run | Inherit analysis |
| Overlay child mode | No overlay allowed | Run or analysis; a run child permits no further overlay |
| Failed-build report, actionable error code/path and triage | Original captured failure, no callback replay for aggregation | Captured evidence plus supported aggregate retry history |
| Experimental artifact export | Existing codec supports run subset | Public analysis output exceeds parked codec capabilities; historical codec coverage uses private fixtures |

The selected shared executable roots and resolved values have the same semantics.
Analysis additionally visits unused dependency-only declarations, and may fail on
an invalid unused graph that run never needs. It may also invoke callbacks for
those declarations. Failed analysis builds may perform diagnostic retries; callback
counts are not promised equal to run for either additional orphan work or failure
aggregation. Neither mode activates application constructors during compilation.

## Validation and evidence safety

Mandatory structural checks, entrypoint/boundary/lifetime checks and build-mode
rules execute in both modes. Registered validation-only rules never block run.
An analysis build does not itself invoke validation-only rules: call
`analysis.validation_report()` once to obtain build findings and fresh
validation-only results. Repeated calls intentionally reevaluate those rules;
they do not replay selection callbacks or application constructors. The report
returns issues rather than throwing merely because it contains validation errors.
Build errors still raise `ContainerBuildError` and leave the builder retryable.

CLI inspection/check commands and build matrices request analysis. Check and each
matrix variant call `validation_report()` exactly once. An already-built run
runtime is rejected when analysis is requested; tooling never silently rebuilds it.
Compilation profiling accepts `--mode run|analysis`, defaulting to run.

Existing temporary component views, selection/decorator facts, graph relationships
and warmup/instrumentation evidence remain conservatively available through their
existing callback consumers. Public builds with registered build rules capture
rich temporary diagnostic evidence as well, then release it on successful run
completion. Escaped temporary inspection graphs retain the established explicit
expiration behavior; caller-owned component snapshots retain existing lifetimes.
Task 11 must audit all arbitrary callback/evidence consumers before reducing any
of this construction or lifetime. This is a public policy/retention migration,
not a claim that compiler allocation minimization is complete.

## Migration examples

```python
# Application startup: no graph inspection or future composition retained.
builder.set_provider_roots(())
runtime = builder.build()

# Tooling: fresh composition, complete analysis, one full-validation pass.
analysis_builder = make_builder()
analysis_builder.set_provider_roots(())
with analysis_builder.build(mode="analysis") as analysis:
    report = analysis.validation_report()
    assert report.is_valid
    manifest = analysis.graph.manifest(all_roots=True)

# Overlay composition requires an analysis parent.
with make_builder().build(mode="analysis") as parent:
    overlay_builder = parent.new_scope_builder()
    overlay_builder.register(ExtraService)
    with overlay_builder.build() as child:
        child.resolve(ExtraService)
```

There is no supported hybrid such as run with a retained blueprint or analysis
without diagnostics. Private compiler switches remain implementation details for
staged optimization and historical regression evidence, not a migration API.
