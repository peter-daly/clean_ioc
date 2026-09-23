# M03 implementation verification handoff

Status: Implementation verification passed; independent Astra review and coordinator checkpoint pending.

Implementation agent: `/root/m03_implementation`, `gpt-6-astra`, high reasoning. Search agent: `/root/m03_search`,
`gpt-6-luna`, low reasoning. Accepted predecessor M02: `fa33b7f`; accepted M03 search checkpoint and implementation
baseline: `37a22f23a3c26824461ae1f55d0d56a99af21ad7`. Branch: `codex/decorator-templates`.
The coordinator owns commits, review, execution log, and milestone status. This implementation agent made no commits.

## Delivered files and behaviour

- `clean_ioc/service_groups.py`, `clean_ioc/__init__.py`: immutable public `DerivedServices(Contract)` alongside
  identity-based `ServiceGroup`. Neither declaration holds builder state or a membership snapshot.
- `clean_ioc/_service_targets.py`: shared pure selection/projection interface and frozen `_ServiceTarget` result.
  Explicit membership is checked first by declaration identity. Automatic selection requires the registered service's
  explicit nominal inheritance, including protocol bases; implementation compatibility or structural protocol matching
  cannot grant participation. Closed contract mismatch means automatic nonselection, but invalid explicit membership
  is an error. Closed registered service contracts remain authoritative even through implementation lookup keys.
- `clean_ioc/generic_utils.py`: identity-based type-expression binding, nested substitution, correct rebuilding of
  `typing.Callable` parameter lists, and nominal projection pruning. Fixed/reordered/multilevel generic bases, aliases,
  repeated variables, generated concrete subclasses, consistent diamonds and same-named distinct TypeVars retain
  their actual declaring identities. Conflicting inheritance paths, unresolved concrete requests and ambiguous
  variable assignments fail instead of choosing an arbitrary mapping. Existing name-based generic factory/decorator
  machinery is unchanged; using-typetoolbox skill was applied and its name-keyed limitation deliberately isolated.
- `clean_ioc/container.py`: compiler adapters retain original registration identity through factory/pattern
  specialization and validate deferred group constraints at `_compile_registration` for each concrete compiled
  request. This covers constructors, factories, structural patterns, discoveries, fallback registrations and aliases.
  The finite candidate adapter preserves input order and deduplicates original definition/canonical request/owner
  tuples. It never enumerates hypothetical specializations, infers group membership, grants visibility, or registers
  public base-service aliases. Ordinary `_decorator_service_matches` and normal decorator activation are unchanged.
- `tests/test_service_targets.py`: 30 cases including projection equivalence, membership/nonmembership isolation,
  immutable mappings, static factory/instance selection, unrelated-service exclusion even through implementation
  lookup, protocols, generated/aliased classes, same-name variables within and across inheritance edges, repeated
  variables, source-independent decorator-expression binding, conflicting diamonds, actual closed-request build
  failures, pattern definition IDs, nested unions/Callables, deterministic candidate streams, post-declaration
  discovery, fallback constraints, ordinary-decorator regression and version-conditional PEP 695 syntax.

## M04/M05 interface

Use `_Compiler._select_service_target(selector, registration, layer, requested_service_type)` at an already available
candidate/occurrence. It returns `_ServiceTarget | None` and wraps failures as `ContainerBuildError` with registration,
request and selector context: `service-group-incompatible` for explicit membership or `service-target-projection`
for automatic selection/projection failures. Nonmembers are excluded before projection, so an unrelated/nonmember
cannot cause a generic projection failure. `DerivedServices` closed-contract mismatches simply return `None`.

The result contains:

- `registration_id`: original definition ID, including when the passed registration has a specialized factory/pattern ID.
- `requested_service_type`: the exact input request key, retaining an explicitly supplied alias; it is the wrapped key.
- `registered_service_type`: normalized original registered service contract, never inferred implementation membership.
- `projected_contract`: concrete specialization of the selector's contract origin.
- `bindings`: immutable map from the contract origin's actual TypeVar objects to concrete arguments.
- `declaration_bindings`: separate immutable map for variables explicitly used in the selector expression. For example,
  `Contract[V, V]` over `Contract[int, int]` has declaration binding `V -> int` and origin bindings `T -> int, U -> int`.

For a finite already-visible stream, `_Compiler._select_service_targets(selector, candidates)` takes
`(registration, layer, request)` tuples and returns selected results in first-seen order. It deduplicates only within
that call; call it independently for independent templates. It does not discover requests or select registry winners.
The caller must retain ordinary visibility, definition-area and occurrence context; do not use it to bypass boundary
selection. Type aliases canonicalize only for duplicate keys, while the first result preserves its original request.

`_bind_typevar_identities(pattern, concrete)` returns a TypeVar-keyed dictionary, `None` for concrete mismatch, or raises
`_TypeBindingError` for ambiguity/unresolved/unsupported inference. M05 can bind a decorator's decorated-argument
contract expression to `target.projected_contract` using the decorator's own variables. Then
`_resolve_typevar_identities(annotation, bindings)` substitutes those exact identities in its annotations. Do not merge
this with source maps or legacy string-keyed maps. M03 tests prove independent variables sharing a name remain distinct;
M05 still owns decorator constructor/factory specialization, checking all remaining variables, and activation.

For M04 source metadata, `_project_service_type(implementation, base)` remains the static projection seam, preserving
unresolved variables. Pair a projected alias's arguments with that base origin's `__parameters__` to expose an immutable
identity-keyed source map. Unknown factory implementation types must remain unknown; never activate them to infer types.

## Verification actually run

Final checks on repository `.venv` Python **3.14.4**:

1. `.venv/bin/python -m pytest tests/test_service_targets.py tests/test_service_groups.py tests/test_provider_maps.py tests/test_registration_patterns.py tests/test_closed_generic_constructors.py tests/test_container.py tests/test_type_alias_lookup_paths.py tests/test_type_aliases.py tests/test_decorator_template_feasibility.py tests/test_boundaries.py tests/test_bundles.py -q --disable-warnings --maxfail=3`
   — **352 passed in 2.14s**.
2. `.venv/bin/ruff check clean_ioc/_service_targets.py clean_ioc/generic_utils.py clean_ioc/service_groups.py clean_ioc/container.py clean_ioc/__init__.py tests/test_service_targets.py`
   — **passed**.
3. `.venv/bin/ty check clean_ioc/_service_targets.py clean_ioc/generic_utils.py clean_ioc/service_groups.py clean_ioc/container.py clean_ioc/__init__.py tests/test_service_targets.py`
   — **passed**, no diagnostics. Narrow fixture suppressions cover intentional same-name TypeVars, inconsistent generic
   inheritance and runtime construction of unsupported variadic type expressions.
4. `.venv/bin/ruff format --check clean_ioc/_service_targets.py clean_ioc/generic_utils.py clean_ioc/service_groups.py clean_ioc/container.py clean_ioc/__init__.py tests/test_service_targets.py`
   — **6 files already formatted**.
5. `git diff --check` — **passed**.

Python **3.11.13** portability used the existing installed interpreter with an isolated temporary uv environment,
without changing repository dependencies, lockfiles or `.venv`:

`uv run --no-project --isolated --python 3.11 --with pytest==9.1.1 --with pytest-asyncio==1.4.0 --with funcie==0.2.0 --with typetoolbox==0.4.0 --with typing_extensions==4.16.0 python -m pytest tests/test_service_targets.py tests/test_service_groups.py tests/test_decorator_template_feasibility.py -q --disable-warnings --maxfail=3`

— **57 passed, 1 skipped in 0.18s**. The sole skip is the explicitly version-conditional PEP 695 test, which passed on
3.14. No unavailable or skipped check is counted as a pass. Full supported-version matrix and `make ci` remain M10.

Early test-only failures used a builder after successful build or assumed pattern entrypoint marking creates a new
request. Fixtures now use independent builders and concrete consumer dependencies respectively, preserving existing
single-use-builder and pattern-entrypoint semantics. No production change was made to accommodate those fixture errors.

## Explicit limits and remaining work

- M03 adds selection/projection and membership validation, not decorator-template registration, expansion, activation,
  source metadata views, provenance diagnostics or boundary/overlay policy changes. These remain M04 onward.
- No infinite/open request enumeration. Existing registration lookup rules still decide which definition is available
  for a concrete request; this interface does not broaden ordinary structural-pattern or open-alias lookup semantics.
- ParamSpec and TypeVarTuple inference is unsupported and fails with an explicit parameter-kind message. Ordinary
  TypeVar domains use nominal class bounds/constraints; uncheckable parameterized or protocol domains fail explicitly.
- Union-variable matching supports unique disjoint partitions of concrete union members, including one variable
  absorbing multiple remaining members. Multiple surviving assignments fail as ambiguous. Inference requiring union
  collapse (for example `T | int` inferred from `int`) is unsupported and reported clearly, rather than guessed.
  Equivalent fully concrete unions are order-insensitive. No change is made to legacy factory/decorator union matching.
- Source/decorator variable defaults and complete decorator validation are not introduced here. Unresolved targets do
  not pass this concrete-selection API merely because a later decorator might provide a default.
- No public explanatory docs changed; the documentation comprehension gate is inapplicable. No bark-core files,
  environments or commits changed. Pre-existing unrelated `.work` graph plans remain untouched. Coordinator-owned
  README/execution-log edits were present at baseline and were not edited by this agent.

Independent technical review has not run yet. Coordinator records its actual findings, repairs, acceptance and all
checkpoint SHAs separately; no final acceptance or milestone-completion claim is made here.
