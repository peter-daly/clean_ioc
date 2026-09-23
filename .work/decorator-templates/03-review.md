# M03 independent review

Reviewer `/root/m03_review`, `gpt-6-astra`, high; fresh explicit handoff. Baseline/change: `37a22f2..60cf3a2`. No reviewer edits/commits.

## Round 1: request changes

Independent focused suite: **352 passed**. Additional probes reproduce three P2s:

1. `generic_utils.py:313`: global unsupported-branch state poisons a supported complete union match. `_bind_typevar_identities(list[T | int] | list[int], list[int] | list[bytes | int])` must uniquely bind T=bytes, rather than fail on an abandoned collapsed-union alternative. Track unsupported inference per complete candidate.
2. `generic_utils.py:181`: inherited nested aliases need canonicalization before comparing projections or exposing bindings. `A=TypeAliasType("A",list[int]); Left(Base[A]); Right(Base[list[int]]); Diamond(Left,Right)` falsely conflicts. A generic inherited `Child(Base[A[T]])` specialized at int cannot join Base[list[int]]. Add canonical alias and diamond cases.
3. `generic_utils.py:276`: `_bind_typevar_identities(T | int | str, int | str)` returns None, silently excluding DerivedServices rather than reporting unsupported union collapse. Diagnose possible collapse; keep provable fixed mismatch nonselection.

Registration identity, factory/pattern membership retention, nominal selection and ordinary decorator behavior showed no further findings. Original implementation agent assigned repairs; acceptance pending.
