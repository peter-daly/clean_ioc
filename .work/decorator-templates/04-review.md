# M04 independent review

Reviewer `/root/m04_review`, `gpt-6-astra`, high; fresh explicit handoff. Reviewed `f831e3a..3e7e3dc`, no edits/commits.

## Round 1: request changes

Independent **145 focused tests passed** (expansion,feasibility,targets,boundaries,ownership). Additional alias probe passed: two exposed aliases yield one candidate retaining original ID/service/name. Two independently reproduced P2s:

1. `container.py:7712`: `getattr(instance,"__orig_class__",...)` executes dynamic lookup/descriptors after registry mutation. A raising __getattr__ leaves partial ordinary registration even without templates. Capture/validate static evidence without user code before mutation; test raising lookup, descriptor and valid generic instance alias.
2. `container.py:3634`: source-root enrichment handles instances only. Typed factory()->Backend[int] under Source gives RegistrationInfo Backend[int] but filter Component Source, incorrectly rejecting cf.implementation_type_is(Backend). Enrich canonical source inspection from known factory evidence, preserving normal runtime views. Test closed/postponed annotations,broad returns and nonexecuted sentinel factories.

Original implementation agent assigned repairs. The internal M04/M05 split is appropriate; actual generated selector boundary recheck remains mandatory M05 work. Acceptance pending.

## Round 2: accepted at `65792c2`

Both P2s resolved. Independent **147 tests passed** plus original instance regression, postponed closed factory and PEP695 generic-instance probes. Static capture occurs before mutation without dynamic lookup/descriptors; source filter metadata agrees with RegistrationInfo while ordinary views stay unchanged. No remaining M04 blockers. Actual generated semantics/boundary recheck remain required M05 before public API exposure. No reviewer edits/commits.
