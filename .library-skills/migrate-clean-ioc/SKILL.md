---
name: migrate-clean-ioc
description: Migrate Python applications from Clean IoC 1.x to 2.x using the bundled conservative codemod and the V1-to-V2 upgrade guide. Use for upgrade requests involving V1 Container, Lifespan, dependency settings, filters, scopes, or FastAPI integration; use use-clean-ioc for new V2 code.
---

# Migrate Clean IoC 1 to 2

Read [references/migration-map.md](references/migration-map.md) before changing an application. The source checkout's `V1_TO_V2_UPGRADE.md` has the full guide; read it when available. The installed V2 package and its public signatures are authoritative if a guide and package differ. V2 requires Python 3.11 or newer.

Run the bundled codemod against application source to preview safe mechanical changes:

```bash
python <path-to-this-skill>/scripts/migrate_v1_to_v2.py path/to/app
python <path-to-this-skill>/scripts/migrate_v1_to_v2.py --write path/to/app
```

The script previews a diff by default. `--write` applies the same edits; `--check` exits nonzero when edits or manual-review findings remain. It only rewrites a straight-line `Container()` registration block followed immediately by a resolve, imported `Lifespan` members, and literal-only `dependency_config` dictionaries on supported builder methods. It reports other V1 constructs and superseded V2 build-mode/inspection calls with file and line numbers; semantic analysis migration remains manual. Run it again after edits; a clean second run should propose no changes.

Review every changed composition root. A builder must finish registrations, decorators, pre-configurations, slots, and bundles before `build()`. Move later mutations before build or model late values as declared scope slots; use `ScopeBuilder(parent, composition=handle)` with a separately retained declaration handle for child composition. The codemod cannot infer those choices.

Rewrite V1 `DependencySettings`, registration/node filters, callbacks, mutable scopes, generic discovery fallbacks, injected container services, and framework setup using the upgrade guide. In particular, V2 filters receive static `Component` occurrences at build time, and `derive(...)` executes at build time; do not carry runtime-dependent callbacks across unchanged. Prefer public APIs only.

Run the affected application's tests using fresh composition factories. Production `build()` emits execution only: it does not run validation rules or safety checks. Call `verify()` separately for missing, circular, captive, factory and custom-rule findings, then inspect `result` and its completeness. Use `result.create_runtime()` under result ownership when tests need both inspection and resolution without recompilation. Every admitted attempt consumes its builder; repair by creating a fresh one. Register all rules with `add_validation_rule(rule)` without a phase argument. Check scope ownership and cleanup. Finish with the application's normal type, lint, and test checks. Do not treat a successful codemod run as proof that the migration is complete.

## Migrating the RC5 analysis API

Replace `builder.analyse()` with `builder.verify()` for root and scope builders.
Replace `AnalysisResult`/`AnalysisReport` imports with `VerificationReport` and
`result.report.assert_valid()` with `report.assert_valid()`. Read findings and
completion directly. Related outcome/error names use the `Verification` prefix.
Keep `create_runtime()` and report context management for execution tests, and
use `--operation verify` for CLI profiling. Do not introduce compatibility aliases.
