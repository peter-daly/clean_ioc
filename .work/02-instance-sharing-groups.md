# 02 — Instance-sharing groups

Status: Implemented in working tree; Sol review thread requested but not readable  
Priority: P0  
Dependencies: 01 semantic references and index  
Enables: 03 cache scenarios; 07 lifespan consequences; 08 cache observations

Implementation notes:

- Added `SharingGroup`, `SharingReport`, and `ContextualCacheFinding` report types in `clean_ioc.graph_analysis`.
- Added `CompiledGraph.sharing_report()` and `clean-ioc sharing` with text, JSON, and Mermaid output.
- Groups use compiled registration/owner facts internally and export semantic group references plus occurrence paths,
  not raw registration IDs, cache keys, owner tokens, runtime scope IDs, configured values, or object representations.
- Sharing conditions distinguish uncached transient activation, per-resolution, scoped, singleton-owner, and supplied
  identity semantics.
- Verification run: `uv run python -m ruff check clean_ioc tests/test_compiler_tooling.py`; `uv run pytest -q`
  (458 passed, 1 upstream FastAPI/Starlette warning).

## Outcome

Explain which graph occurrences use the same effective cache key, under what runtime conditions they share an
instance, and whether different occurrence plans compete to initialize that shared instance.

```text
Database — singleton
  7 occurrences use one root-owned cache group.

Repository — scoped
  Sharing depends on the effective scope cache and inherited cached values.

Formatter — transient
  Each activated dependency edge constructs a new instance.
```

This is static sharing eligibility, not a live heap diagram. Never promise object inequality for arbitrary factories:
two uncached factory calls may return the same application-owned object.

## Current foundation

Steps cache by registration ID, with per-resolution context, effective scope, or declaring singleton owner selecting
the cache. `Component` exposes occurrence identity and ownership categories. `Scope._find_scoped()` implements parent
inheritance; `ScopeBuilder` creates a new scoped-cache boundary. Closed generic specializations have distinct IDs.
The graph currently does not expose a safe, complete grouping of these facts.

Primary integration points: `_RegistrationStep` subclasses, `_PlanSet`, `_finalize_plan()`, `_RuntimeOwner`, `Scope`,
`ScopeBuilder`, `components.py`, the new `graph_analysis.py`, and ownership tests.

## Proposed model and API

- `SharingGroup`: deterministic public group reference, occurrence paths, cache category, semantic declaring owner,
  closed service identity, and sharing conditions.
- `SharingReport`: groups plus `ContextualCacheFinding` records.
- `ContextualCacheFinding`: competing occurrences, fields known to differ, evidence paths, and certainty
  (`different`, `equivalent-structure`, `unknown-values`).

Proposed entry point: `graph.sharing_report()` with text/JSON and an optional condensed Mermaid sharing projection.
The default occurrence view remains available; a group view must link back to every original occurrence.

Do not export actual registration IDs, runtime scope IDs, cache keys, or owner tokens. Internally group using real
compiler identities; derive graph-local export references from canonical semantic paths. Equal service types alone do
not establish sharing, and exported group references are not promised stable across arbitrary graph edits.

## Implementation stages

### 1. Capture accurate cache identity

- [ ] Add a frozen internal analysis binding between occurrence paths, executable registration identities, and declaring
  owner identities. Build it during plan finalisation; runtime steps must not perform analysis lookups.
- [ ] Account for cloned component trees pointing to anchored steps and synthetic provider roots reusing target steps.
- [ ] Keep separate same-type registrations separate, and group repeated occurrences of one closed registration.
- [ ] Treat supplied instances as supplied identity semantics, not as proof that the constructor runs once.

### 2. Define sharing conditions by lifespan

- [ ] Transient: no container cache; activation occurs per executed edge.
- [ ] Per-resolution: same registration shares within one resolution context. Each typed-provider invocation begins a
  new context, so sharing does not cross provider calls.
- [ ] Scoped: sharing depends on the active scope, its cache, and existing inherited values. Do not state that every
  nested scope has a unique object or that all descendants necessarily share one object.
- [ ] Singleton: group by registration and declaring root/overlay owner. Explain that separate container builds have
  separate owners and overlay-owned singletons do not become root-owned.
- [ ] Represent shared pre-configuration completion state separately from instance-cache groups.

### 3. Detect competing occurrence plans

- [ ] Compare selected dependency identities, decorator order, argument-policy categories, and ownership structure for
  occurrences that map to the same cache group.
- [ ] Report proven structural differences as informational/warning findings: the first successful activation determines
  the cached result reused later. Do not change cache semantics or split registrations automatically.
- [ ] For configured values, use only a private, conservative comparator for exact built-in scalar types where safe.
  Never invoke arbitrary `__eq__`, `repr`, hashing, or serialization. Export only that a difference was established,
  never the values or their hashes. Unknown comparisons must remain unknown.
- [ ] Avoid claiming behavioural equivalence from equal structural plans; factories can have arbitrary behaviour.
- [ ] Keep these findings opt-in through analysis or explicit validation rules, not new mandatory build errors.

### 4. Present and document

- [ ] Add `clean-ioc sharing TARGET [--path PATH] --format text|json|mermaid`.
- [ ] Give occurrence and sharing views distinct labels and preserve expansion links/reference paths.
- [ ] Add examples showing context-derived transient values versus cached values, sibling/nested scopes, provider calls,
  and tenant overlays. Explain first-successful-activation behaviour without implying which concurrent caller wins.

## Verification

Construct a diamond graph and prove distinct occurrence steps group under the same singleton cache while separate
registrations remain separate. Cover nested scopes both before and after parent activation, sibling scopes, fresh
overlay cache boundaries, inherited singletons, closed generics, same-type supplied instances, providers, and shared
initializers. Exercise different contextual dependency selections and safe scalar argument differences. Use hostile
objects whose equality/representation methods raise to verify analysis never inspects user values unsafely.

Verify no exported raw IDs/tokens/values and no default fingerprint change. Confirm reporting does not activate any
component or mutate caches. Measure analysis separately; normal cache-hit performance must remain unaffected.

## Acceptance criteria

- Every cached registration occurrence belongs to a correctly qualified group with readable sharing conditions.
- Condensation never loses contextual paths or merges merely equal service types.
- Competing wiring is explained conservatively, without leaking values or changing resolution behaviour.
- Static reports clearly distinguish possible sharing from runtime instance observations.
