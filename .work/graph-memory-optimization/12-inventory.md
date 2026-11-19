# Task 12 — direct decorator selection facts

## Construction and consumer boundary

`_Compiler._compile_decorators` visits each generated decorator against each
completed core occurrence. `_select_service_target` already caches pure
membership/projection with identity-safe keys and strongly held inputs. User
`when` and position callbacks still run for each actual occurrence. Their outcomes,
filter descriptions and exceptions are recorded at their original call sites.

Previously, diagnostics-off capture constructed occurrence-specific
`TemplateDecision` and `CandidateDecision` objects, then
`_capture_decorator_pattern` used `dataclasses.replace` to normalize every template
and decision to occurrence zero. Most are identical selector rejections. The
pattern pool subsequently discarded these duplicate normalized objects.

The scoped candidate checks a compiler-local template pool before constructing
labels, binding tuples or `TemplateDecision`. A separate rejection pool reuses only
the constant `template-target-not-selected` decision. Selected, predicate-rejected
and failed-callback decisions still capture the actual call's description and
outcome. No selection, applicability or position callback is cached or replayed.

The existing `_RemappedDecoratorExplanation` continues to carry the occurrence
outside the shared facts. Capture receives that occurrence explicitly; there is
no temporary compiler field, AST transformation, or new deferred public view.
Public explanations still materialize exact target occurrence IDs from captured
immutable facts. The existing materialization cost remains; this task introduces
no additional inspection cache or repeated-inspection allocations.

## Pool keys and owners

| Pool | Key | Value and owner |
| --- | --- | --- |
| Template facts, diagnostics off only | `id(candidate)`, `id(target)`, `id(core.service_type)`, `id(original_target_registration)`, `id(boundary)` | Explicit tuple holding all five identity inputs and the immutable public fact; compiler only |
| Constant selector rejections, diagnostics off only | `id(template_fact)` | Immutable public decision strongly holding that fact and original declaration origin; compiler only |
| Existing decorator patterns | Subject, ordered selected tuple, ordered rejected tuple | Existing immutable explanation pattern; referenced by occurrence views |

Integer identities avoid application-defined hashing/equality, including for
string subclasses used as boundary names. Strong identity owners prevent address
reuse. Candidate sources
already belong to the blueprint and service-target inputs already belong to its
compiler-local cache; no key is copied into a runtime graph or retained global
cache. Compiler teardown releases both new pools. Captured immutable facts may
outlive the pools through supported detached inspection snapshots.

## Rich history boundary

Analysis and public run builds with arbitrary build rules enable diagnostics.
Their `TemplateDecision.target_occurrence_id` is an original occurrence identifier;
rich history and census retain explanation identity. The candidate leaves these
paths eager and does not populate either new pool. Sharing a payload while keeping
that public dataclass field would require a larger representation change and
artifact compatibility work. Exact repetition is measured separately rather than
assuming the normalized diagnostics-off counts apply here.

All task 10/11 capability, rule, failure witness and inspection expiration contracts
remain unchanged. No activation-cache, draft, temporary-index or callback-snapshot
ownership optimization is included.
