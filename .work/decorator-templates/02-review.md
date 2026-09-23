# M02 independent technical review

Reviewer: `/root/m02_review`, `gpt-6-astra`, high reasoning, fresh explicit handoff.
Reviewed boundary: `9cb82d7..799d528`. Independently reran focused suite: **319 passed**.

## Round 1: request changes

1. P2, `container.py:107–117`: positional generic argument comparison rejects equivalent unions. `register(list[int | str], instance=[], groups=[ServiceGroup("g", service_type=list[str | int])])` must succeed; the keys compare equal. Add a PEP 585 regression because ordinary Generic subscription caching can hide the defect.
2. P2, `container.py:108–109`: Callable argument lists are treated as opaque values, rejecting `Service[Callable[[T], int]]` against `Service[Callable[[str], int]]` prematurely. Recurse into parameter lists, defer unresolved variables to M03, and keep concrete mismatch rejection.

Identity declarations, membership propagation, discovery cache prevalidation, aliases, overlays, factory/pattern specialization IDs, and provider-map separation otherwise inspected without findings. Reviewer made no edits/commits. Repair assigned to the original implementation agent; acceptance remains pending.

## Round 2: request changes

Reviewed `799d528..541f611`; independent **321 tests passed** and both original findings resolved.
One related P2 remains at `container.py:123`: `Service[T | int]` grouped under `Service[int | str]` must defer unresolved union constraints because `T=str` satisfies them. Positional comparison incorrectly treats the fixed int/str pair as a definite conflict. Add conservative unresolved-union deferral and regression, retaining concrete mismatch rejection. Original implementer assigned repair; acceptance pending.
