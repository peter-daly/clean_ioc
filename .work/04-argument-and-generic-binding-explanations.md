# 04 — Argument and generic-binding explanations

Status: Implemented and independently reviewed; documented failed-specialization limitation (2026-09-12)  
Priority: P1  
Dependencies: Existing compilation explanations; 01 graph references  
Enables: Richer 05 failure graphs and 07 change explanations

## Outcome

Explain how each parameter moved from its declared annotation and Python default to its compiled value or selected
dependency. For generics, show canonicalization, the selected template, type-variable bindings, and substituted
dependency annotations without exposing configured values or rerunning composition callbacks.

```text
SqlRepository.timeout
  Annotation: int
  Policy: derive
  Result type: int
  Evaluation phase: compilation
  Value: redacted

Serializer[list[Order]]
  Selected pattern: Serializer[list[T]]
  Pattern binding: T → Order
  Compiled argument item_serializer: Serializer[Order]
```

## Current foundation

`CompilationExplanation`, `CandidateDecision`, and `DefinitionOrigin` already record safe selection evidence.
`_compile_dependency()` recognizes fixed/default/derived/select policies. `build_arg()` and `generic_arg()` are
implemented using policy machinery, so preserve their semantic category before lowering loses that distinction.
Factory specialization and structural pattern matching already calculate bindings, but the public service mapping
and factory-pattern mapping are not interchangeable.

Primary integration points: `arguments.py`, `_arguments_to_dependency_config()`, `_compile_dependency()`,
`_specialize_factory()`, `_specialized_factory_dependencies()`, `_compile_decorators()`,
`_compile_pre_configurations()`, `tooling.py`, and generic/type-alias tests.

## Proposed model and API

- `ParameterExplanation`: owner reference, parameter name, declared/canonical annotation, default-presence flag, policy
  kind, evaluation phase, result category/type, selected component references, and provenance.
- `GenericBindingExplanation`: requested service, template identity, selected tier, service bindings, factory-pattern
  bindings, before/after dependency annotations, and specialization failures where available.
- Policy kinds: implicit injection, Python default, fixed, select, inject, derive, build argument, and generic argument.
- Result categories: fixed value, component edge, slot, collection, provider, or runtime context.

Proposed methods: `graph.explain_arguments(component)` and `graph.explain_specialization(component)`. Extend the existing
`explain` CLI with `--arguments` and `--specialization`, plus optional `--argument NAME` after selecting an occurrence.
Existing `graph.explain()` and its text/JSON shape remain supported.

## Implementation stages

### 1. Preserve policy intent

- [ ] Add immutable private policy-origin metadata where helper policies are created; do not introspect closures later.
- [ ] Carry policy category through registration, generic specialization, decorators, and pre-configuration lowering.
- [ ] Preserve declared versus canonical annotation and distinguish a missing default from an explicit `None` default.
- [ ] Record whether `inject()` or `select()` bypassed a Python default without serializing that default.
- [ ] Keep build-input key names private. Public explanation says "explicit build input" without key, value, hash,
  presence/absence details beyond the existing failure contract, or callback closure content.

### 2. Capture outcomes during compilation

- [ ] Store explanations by exact occurrence and parameter after each outcome is known. Fixed and derived values share
  a value step but retain different explanation categories.
- [ ] Record selected component references and existing candidate decisions for injection/selection outcomes.
- [ ] Capture generic bindings at the point they are computed, preserving service versus pattern-variable scopes and
  rejecting ambiguous textual presentation of distinct same-named variables.
- [ ] Explain exact registration, structural pattern, and open fallback selection, including rejected less-specific
  templates and unresolved/conflicting bindings using existing reason codes where applicable.
- [ ] Include closed generic constructors, inherited substitutions, aliases, and explicitly registered union keys.
- [ ] Capture failure context without re-evaluating a derivation. Build-time derivations may run again during the
  existing diagnostic retry path; explanation rendering itself must not cause additional calls.

### 3. Freeze, expose, and render

- [ ] Attach a frozen explanation sidecar to the compiled graph; do not add configured-value information to manifests.
- [ ] Return a clear unsupported/not-recorded result for unavailable legacy/internal explanation detail rather than
  reconstructing it through user code.
- [ ] Render short parameter summaries and expandable generic substitutions in text/JSON; keep provenance optional.
- [ ] Preserve root versus dependency-occurrence distinctions and display source side for cross-boundary selection.

### 4. Documentation and compatibility

- [ ] Add a parameter-policy comparison example, a default-bypass example, and a nested generic-pattern walkthrough.
- [ ] Document which facts were recorded versus inferred, and retain the current type-alias/NewType identity semantics.
- [ ] Keep explanation metadata out of semantic fingerprints; equivalent executable wiring should not differ solely
  because the developer used a different explanatory helper.

## Verification

Cover every policy with constructors, factories, decorators, and pre-configurations. Include explicit `None`, a callable
fixed value, missing build input, failed derivation, collection selection, providers, slots, and default override.
Generic tests include nested/repeated variables, bounds, conflicting variables, closed constructors, inherited generic
bases, alias reordering, NewType, and structural pattern specificity. Assert service and pattern bindings are displayed
separately in the `Serializer[list[Order]]` case.

Use sentinel secrets in build keys, values, defaults, closure state, and object representations; recursively inspect
every new serializer and renderer. Verify post-build inspection invokes neither predicates nor derivation functions.
Check deterministic output and unchanged default manifest fingerprints.

## Acceptance criteria

- Every supported parameter policy produces an accurate recorded explanation at its exact occurrence.
- Generic explanations show the substitutions actually used to compile dependencies.
- Values and build-input identifiers remain redacted; arbitrary user representations are never evaluated.
- Existing explain APIs and normal execution behaviour remain compatible.
