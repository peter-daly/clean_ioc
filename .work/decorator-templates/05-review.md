# M05 independent technical review

Reviewer `/root/m05_review`, `gpt-6-astra`, high, fresh explicit handoff. Reviewed `e6bd146..1c508ea`; no edits/commits.

## Round 1: request changes

Independent **537 focused tests passed**. Three executable P2 probes:

1. `container.py:2595`: merging all base projections into one TypeVar-keyed source map loses declaration scope when the same object is reused. `Base(Generic[T]); Wrapper(Base[list[T]],Generic[T])`, overriding constructor inner:Op[T], cannot wrap Op[int] even with Wrapper[int]. If the constructor is inherited from Base, wrapping Op[list[int]] incorrectly creates Wrapper[list[int]]/Base[list[list[int]]] instead of Wrapper[int]. Separate constructor declaration scope and implementation-parameter inference. Test both forms and runtime specialization.
2. `container.py:2628`: single-step substitution leaves dependent defaults order-sensitive. T; U default=T; V default=U; callable wrapper(inner:Op[T],later:V,earlier:U)->Op[T] fails generated decoration of Op[int] with int dependency42, while ordinary decoration succeeds. Resolve identity-keyed defaults transitively with cycle protection independently of annotation order.
3. `container.py:6157`: generated when RuntimeError is rethrown raw, producing compile-error with target-only path. Preserve safe target/template/source provenance and original cause through diagnostic retries; ordinary predicate handling unchanged.

Runtime order, exact sources, boundary feedback, snapshot and cleanup coverage otherwise sound. Original implementation agent assigned repairs; acceptance pending. Full overlay acceptance remains M06; no public docs gate.

## Round 2: accepted at `f9cbaee`

All three P2s resolved. Independent **546 focused tests passed**; original probes now pass, including runtime class specialization for inherited/overridden constructors and open/closed aliases, dependent defaults, and safe predicate provenance/original cause. Independent Ruff/ty passed. No remaining M05 blockers; full overlay acceptance remains M06. No reviewer edits/commits.
