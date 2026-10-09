# Per-call component scopes

Status: Complete, including independently reviewed private abstract helpers and class-shape/escaped-result hardening.
Baseline: `d61505b` (2.0.0b17), branch `codex/per-call-scopes`.

## Objective and agreed public API

Replace handwritten wrappers such as Bark's `ScopeWrappingMessageProcessor` with a scope policy on one ordinary
component registration. Consumers keep depending on, resolving, and calling their existing service interface.
There must be no second user registration, special registration name, injected runner type, or public proxy factory
required to use this feature.

```python
builder.register(MessageProcessor, ActualMessageProcessor, scope="per_call")
processor = container.resolve(MessageProcessor)
await processor.process_message(message)
```

Each method invocation creates an isolated operation scope, activates the actual implementation from its frozen
plan in that scope, invokes the same method with unchanged arguments, and closes the scope after completion.
Obtaining the service handle does not instantiate its target. This is per-invocation scoping, not eager activation
inside a scope that has already closed when `resolve()` returns.

Public declaration types:

```python
Lifespan = Literal["transient", "per_resolution", "scoped", "singleton"]
LifespanPolicy = Lifespan | Literal["auto"]
ScopePolicy = Literal["current", "per_call"]
```

Use `lifespan: LifespanPolicy = "auto"` and `scope: ScopePolicy = "current"` on component registration APIs.
Keep `Lifespan` as the four concrete runtime lifespans. Export the new policy aliases publicly.

| Scope | Declaration lifespan | Compiled implementation lifespan |
| --- | --- | --- |
| current | auto | per_resolution (existing default behavior) |
| current | explicit concrete lifespan | that lifespan |
| per_call | auto or scoped | scoped |
| per_call | transient, per_resolution, singleton | configuration error |

`None` is not the new default and is not a valid new registration policy. Invalid strings also fail clearly.
Preserve the distinction between a declared policy and its effective lifespan where builder edits require it;
compiled component lifespan fields must never contain `auto`.

## Scope and implementation decisions

1. Support `ContainerBuilder`, `ScopeBuilder`, boundary builders, and the shared `ComponentBuilder` protocol.
   Carry policy consistently through `register`, `register_pattern`, `register_subclasses`, and
   `register_generic_subclasses`, their discovery materialization and generic specialization. Existing calls
   without the new policy retain their behavior. Provider-map registrations retain their explicit internal
   transient policy; do not turn synthetic maps into per-call services.
2. Extend `patch_component` coherently: distinguish an omitted scope/policy edit from setting a value, preserve
   the existing compatibility meaning of its omitted/None lifespan edit, and accept `auto` as a lifespan edit.
   Validate the final combined declaration atomically before mutation. Document whether the new scope edit
   is supported; preferred implementation supports it with an omission sentinel and no nullable scope value.
3. Infer forwarding methods from the declared service contract; the agreed API has no required `methods=` list.
   Include inherited public instance methods and `__call__`, preserve argument/result behavior and useful
   method signatures, and dispatch to the real implementation's override. Support method-only Protocols,
   ABCs, concrete service classes, and closed generic contracts without invoking constructors at build time.
   Inspect supported class/type metadata, not an activated object. Reject unsupported contracts with a clear
   build diagnostic rather than exposing a partially usable interface.
   Private abstract helpers must not leave the generated handle abstract: satisfy outstanding private abstract
   members with stubs that raise on direct use, without opening an invocation scope. Public methods still execute
   on the real implementation, whose private helpers work normally. Preserve generated initialization and public
   forwarding, including `__call__`, and cover inherited and name-mangled abstract helpers.
   The generated handle uses safe object representation and identity equality/hash. Reject unsupported contract
   attribute hooks, finalizers, and behavioral special methods at build, naming the offending member. Keep ordinary
   mixins, cooperative `super()`, private slots, closed generics, and private-field dataclasses supported. Inspect
   effective inherited annotations rather than rejecting base declarations that a subclass replaces with `ClassVar`.
   Implementation-only hooks behind a supported contract continue to run on the real instance.
4. Initial support is ordinary synchronous methods and coroutine methods. Reject properties, required public
   instance-data contracts, static/class method operations, and generator/async-generator operations where
   declared/detectable, explaining the unsupported service/member. Do not silently return a stream whose
   resource-owning scope is already closed. Document that arbitrary returned resource-backed objects/lazy
   values must not escape an operation; Python cannot prove all application return-value lifetimes.
   Reject `instance=` with per-call scope because it cannot provide a newly owned implementation each call.
   Reject statically identifiable self/service-returning operation declarations at build. Guard opaque operation
   results at runtime against direct target-instance and bound-method escape, including the real core and each
   decorator in that invocation. Reject before scope cleanup and retain normal cleanup behavior. Do not claim to
   prove arbitrary closures or nested application objects safe, and do not traverse arbitrary application graphs.
5. A normal method uses synchronous activation and cleanup. An async method uses async activation/cleanup and
   awaits the target operation in the caller's task. Reject sync methods whose target plan requires async
   activation or cleanup. Do not add implicit task creation, task supervisors, slot-injection hooks,
   message interpretation, or a callback-policy framework.
6. Each invocation starts a fresh scoped cache even if its parent has already activated scoped resources.
   Reuse the frozen composition and singleton owners without compiling an empty overlay. Do not change ordinary
   `new_scope()` inheritance semantics. Existing declared scope provisions may retain their ordinary inheritance
   rules; this feature does not reinterpret method arguments as injectable scope slots.
7. The target is selected and compiled once; invocation executes the captured inner plan, never ordinary service
   lookup that could resolve the same public wrapper recursively. No builder creation, registration discovery,
   filters, template callbacks, or compilation on each invocation. Legitimate dependency cycles still fail at
   build time; do not globally disable cycle checks to permit the wrapper.
8. Treat the boundary as a deferred lifetime edge. A singleton consumer may retain the handle while its scoped
   target is created per invocation. Target dependencies still obey normal lifespan checks inside that scope.
   A captured root singleton handle anchors to its declaring root plan/owner, even when first resolved through
   a child or overlay. Overlay-owned handles respect the overlay plan and its lifetime. Handles from closed
   owners fail clearly. Do not bind a singleton handle to whichever request first obtains it.
9. Preserve service selection, registration ID, name, tags, group/provider-map contributions, aliases, generic
   bindings, contextual filters, and boundary visibility. There is one public component registration. Internal
   proxy/target occurrences may be represented separately, but cannot become duplicate collection/map entries.
10. Existing decorators and pre-configurations belong to the underlying component's operation plan and execute
    under their normal ordering/lifetime rules. Resolve/construct the decorated target inside each call scope.
    Do not instantiate an inner dependency graph outside the boundary. No additional outer-versus-inner
    decorator API is in scope. Preserve decorator template source/target identity and compilation invariants.
11. Runtime cleanup must cover target activation failure, method failure, async cancellation, sequential and
    concurrent calls. Cleanup ownership must remain correct for async resources and singleton descendants.
    Preserve existing exception/cleanup behavior instead of swallowing failures. Each concurrently active
    call has independent target/scoped state; closing one cannot close another's resources.
12. Graphs and diagnostics must expose the deferred scope boundary truthfully. Validation, manifests,
    fingerprints, impact/activation/sharing analysis must not report the target as eagerly activated or globally
    shared across calls. Keep ordinary registrations' output stable where possible. New representations must be
    deterministic and value-free, with no runtime owner tokens, provided values, or callback closures serialized.
    Keep beta tooling unversioned; document any necessary semantic manifest change.

## Repository map

- `clean_ioc/components.py`: policy aliases, ComponentBuilder protocol, frozen component metadata.
- `clean_ioc/container.py`: builder declarations/snapshots/discovery, policy normalization, target compilation,
  lifespan checking, activation steps, runtime owners/scopes, overlays and explanations.
- `clean_ioc/__init__.py`: exported policy types.
- `clean_ioc/_decorator_templates.py`, `_service_targets.py`, `registration_patterns.py`: preserve composition
  behavior as needed; avoid unrelated redesign.
- `clean_ioc/tooling.py`, `graph_analysis.py`: scope/deferred activation and ownership descriptions.
- `tests/test_per_call_scopes.py` (suggested): behavioral feature coverage; extend existing regression suites
  for integrations rather than duplicating all their fixtures.
- `docs/scopes.md`, `docs/lifespans.md`, relevant API examples, `README.md`, `CHANGES.rst`: usage and compatibility.

Reference application (read-only; do not modify Bark):
`/Users/peter.daly/WS/bark/bark-core/bark_core/messaging/clean_ioc.py` and
`/Users/peter.daly/WS/bark/bark-core/tests/unit/messaging/test_clean_ioc.py`.
The existing wrapper builds one unused overlay to isolate inherited scoped state; the new runtime boundary should
make that workaround unnecessary. Its slot-injecting subclass and task creation are not features to copy.

## Implementation stages

1. Record the concrete design of method discovery, deferred lifetime ownership, and graph representation before
   editing the compiler. If a requirement is incompatible with existing internals, report it with evidence and
   propose the smallest adjustment; do not silently narrow the agreed API.
2. Add declaration policy normalization, exports, public signatures, propagation and atomic builder editing.
   Verify all existing defaults remain per_resolution and all per-call targets normalize to scoped.
3. Add an isolated invocation scope and internal forwarding implementation. Compile the inner target directly,
   preserve ownership, and keep both construction and operation inside the scope.
4. Integrate the deferred boundary with lifetime checks, contextual selection, generics, decorators/templates,
   collection/provider paths, overlays, boundaries, and frozen graph/tooling representations.
5. Add behavioral regression tests, runnable public documentation examples, and changelog documentation.
6. Run required checks and focused measurements; report exact results and limitations.
7. Hand off the completed diff to a separate Sol High reviewer. Resolve findings, rerun affected checks, and
   obtain reviewer verification before marking complete.

## Required acceptance evidence

- API default matrix above, invalid inputs, normalization, and public/protocol signatures agree.
- One registration supplies the unchanged service contract through resolve, injection, collections, providers,
  and maps as applicable. No naming convention or custom user wrapper is needed.
- Resolve/build do not activate the implementation; first invocation does. Capture method args, kwargs,
  return values and raised exceptions; verify inherited operations, overrides and callable services.
- Every invocation uses a new target/scoped dependency identity. Repeated target-graph edges share scoped
  dependencies within one operation. Pre-warm parent resources and verify isolation and separate cleanup.
- Concurrent calls overlap without sharing mutable scoped state; test async and relevant sync concurrency.
- A singleton consumer first obtained from a short-lived child remains usable after that child closes, using
  the root-owned composition. An overlay consumer uses its own dependencies and becomes invalid after closure.
- Genuine captive dependencies and cycles below the boundary still fail, and unrelated current-scope lifetime
  rules are unchanged. Include a transitive invalid dependency to guard against over-broad exemptions.
- Sync and async construction/cleanup, activation failure, method failure, cancellation and closed-owner calls.
- Decorators (including generated templates) activate inside the call, retain order, and clean up correctly.
- Names/tags/contextual selection, closed generics and aliases, discovery/pattern policy propagation, private
  boundary visibility, and overlay target plans remain correct. Cover atomic invalid patch and retry after failure.
- Unsupported method/interface/instance declarations fail during build/registration with actionable diagnostics.
- Inspection can show the scope boundary without activation; activation and sharing reports distinguish handle
  acquisition from target invocation and do not imply target cache sharing across calls.
- A proof that repeated invocations do not call build/compile or rerun selection callbacks.

Run focused feature/regression tests while developing, then `make ci` and `uv run mkdocs build --strict`.
Run focused feature tests on available supported Python versions (3.11-3.14); state any unavailable version.
Use the BenchBro skill and existing compiled-runtime/build cases for a same-machine baseline comparison,
with experiment outputs under ignored `.benchbro/` and no changes to shared committed baselines. Keep
measurements separate from concurrently running test/compiler work. Investigate material regressions rather
than treating noisy percentages as conclusive. Do not create a new benchmark framework.

## Delegation and workspace rules

The user explicitly requested a Sol agent with high reasoning to implement, followed by a different Sol agent
with high reasoning to review. Use `gpt-6-sol`, high, for both. Parent coordinates and owns this plan and any
independent acceptance probes. Implementer owns production changes, normal feature tests, and docs. Reviewer
owns the review report and focused independent probes; fixes go back to implementer unless parent delegates them.
No release, publishing, merging, or unsolicited external messages. No changes to Bark. Preserve the pre-existing
untracked `.work/01-*` through `08-*` files and `.work/README.md`; they belong to unrelated work. Do not rewrite
their status or follow their unrelated model assignments. Do not stage or commit unrelated files.

## Execution log

- Parent created this plan before implementation, on `codex/per-call-scopes`.
- Baseline `make ci`: passed, 743 tests on Python 3.14.4, plus lint/format/type/docs examples/benchmark discovery.
- Baseline performance: completed existing `compiled-runtime` and `compiled-build` cases. Reports under ignored
  `.benchbro/per-call-scopes/{runtime,build}-before.json`; named baselines `per-call-runtime-before` and
  `per-call-build-before`. Some samples were flagged noisy; compare quality before making claims.
- Implementation: delegated to `/root/implement_per_call_scopes`, `gpt-6-sol`, high reasoning.
- Independent acceptance scenarios: parent owns `tests/test_per_call_scope_acceptance.py`, covering singleton
  capture, warmed-parent isolation, async cancellation/cleanup, overlapping synchronous calls, overlay selection,
  and provided scope slots.
- Implementer handoff: `make ci` passed with 772 tests; strict MkDocs build passed; all 29 feature/acceptance tests
  passed on Python 3.11, 3.12, 3.13, and 3.14. No release or commits performed.
- Independent Sol High review: delegated to `/root/review_per_call_scopes`, `gpt-6-sol`, high reasoning.
- Post-change performance: both BenchBro comparison commands exited 0 using the same interpreter/environment.
  Ordinary compiled-runtime medians changed +2.1% to +4.8%, while the direct-Python control changed +8.3%.
  Compiled-build medians changed +5.7% to +7.9%. Several measurements had noise/outlier flags. These are measured
  shifts with environment drift, not proof of zero overhead or an attributable regression. Reports are in ignored
  `.benchbro/per-call-scopes/{runtime,build}-after.json` (and corresponding Markdown files).
- Independent review completed with six findings repaired and no outstanding required fixes. Repairs cover
  coroutine/iterator escape, unsupported descriptors, provision locking, structured return-annotation inspection,
  and the Python 3.11 Protocol backport. Dynamic forwarding and safe eager results remain supported. Evidence and
  residual limitations are recorded in [the review report](09-per-call-scopes-review.md).
- Final verification: implementer reports `make ci` passed with **784 tests**, including the parent's five
  independent acceptance tests; the focused feature/acceptance suite passed **41 tests** on each of Python
  **3.11, 3.12, 3.13, and 3.14**. The strict documentation build also passed. Reviewer independently reran the
  41-test suite and targeted repair probes. Parent verified `git diff --check` is clean.
- Implementation and review used separate `gpt-6-sol` agents with high reasoning as requested. Changes remain
  available in the workspace on `codex/per-call-scopes`; no commits, release, or publishing performed.
- Follow-up requested by user: private abstract helper stubs must raise if used on the handle. Parent reproduced
  the unresolved private abstract member failure and added an independent regression covering inherited,
  name-mangled helpers, abstract initialization, deferred activation, and resource cleanup. The same Sol High
  implementer completed the repair and the independent Sol High reviewer checked it. The generated handle now
  satisfies private abstract methods and properties with `NotImplementedError` stubs, preserving async methods
  and property accessor modes. Public calls continue to use the real scoped implementation. Unsupported abstract
  special methods are rejected at build time; generated initialization and callable forwarding remain intact.
- Follow-up verification: two additional review findings repaired, no outstanding required fixes. Parent's final
  `make ci` passed with **790 tests**; output is in `/tmp/clean-ioc-private-abstract-final-ci.log`. Implementer
  verified **47 focused tests** on each of Python **3.11–3.14**, plus lint, formatting, type checks, and strict
  documentation build. Reviewer independently reran all 47 focused tests and the descriptor/special-method probes.
  Parent's final `git diff --check` passed. Changes remain uncommitted.
- User authorized hardening after parent reproduced unsafe contract attribute hooks, inherited concrete
  representation/finalizer behavior, direct service/bound-method escapes, and a false rejection of inherited
  annotations overridden with `ClassVar`. Same Sol High implementation/review workflow applies. Parent added
  13 acceptance cases and observed each fail before the repair; they cover hook rejection without user-code
  activation, private-field dataclass handle behavior, and sync/async escapes through zero or two decorators.
- Hardening completed: supported handles use safe object representation and identity equality/hash. Unsupported
  contract hooks, behavioral special methods, and reserved-field collisions produce named build errors.
  Effective member/annotation inheritance respects class-variable and method overrides. Bare and quoted
  `ClassVar` annotations work; known self/service result declarations fail at build. Per-call activation records
  core and decorator identities and rejects direct instance/bound-method escapes before scope cleanup, including
  built-in method wrappers. Arbitrary closures and nested objects retain the documented lifetime restriction.
- Independent hardening review found five issues across repair revisions; all were resolved and independently
  rechecked, with no outstanding required fixes. The reviewer reran **78 focused tests** and targeted probes.
  The implementer verified all **78 tests on Python 3.11, 3.12, 3.13, and 3.14**. Parent final `make ci` passed
  **821 tests**, plus lint, formatting, types, docs examples, and benchmark discovery; strict MkDocs also passed.
  Logs: `/tmp/clean-ioc-class-shape-final-ci.log` and `/tmp/clean-ioc-class-shape-final-docs.log`.
- Capture is isolated in `_PerCallTargetRegistrationStep` and `_PerCallResolutionContext`. Parent compared the
  ASTs of ordinary `_RegistrationStep` and `_RuntimeResolutionContext` with `d61505b`: both are unchanged, so
  no extra ordinary-path capture allocation or activation checks were retained. No new benchmark run was needed
  for this follow-up. Final diff check passed; all feature changes remain uncommitted on `codex/per-call-scopes`.
- User-requested benchmark follow-up: added `benchmarks/bench_per_call_scopes.py` comparing retained handles with
  equivalent handwritten sync/async scope wrappers and a two-component container build. Each timed runtime batch
  performs 100 complete activation/invocation/cleanup operations; preflight verified all resources close.
  Two unchanged batched runs measured sync overhead **0.84–0.90 µs (9.4–10.3%)**, async overhead
  **0.74–0.82 µs (7.0–7.9%)**, and build overhead **0.36–0.47 ms (11.7–15.0%)** in this minimal workload.
- Historical measurements used mains power while current measurements used battery, so parent collected a fresh
  original-code baseline from a temporary detached `d61505b` checkout with the same interpreter/dependencies.
  Latest ordinary runtime medians moved **+0.7–2.8%**, with the direct-Python control **+1.9%**; ordinary builds
  stayed within **±0.6%**. These measurements do not show a clear material regression in ordinary paths. Outlier
  flags and repeat variation are retained in [the benchmark report](09-per-call-benchmarks.md) and ignored JSON
  artifacts. The temporary baseline checkout was removed; historical named baselines were retained.
- Benchmark-source lint, formatting, types, full benchmark discovery, and diff checks passed. No production changes
  or commits were made during the benchmark follow-up.
