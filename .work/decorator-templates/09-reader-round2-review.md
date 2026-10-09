# Fresh reader round 2 — verbatim Phase A

Agent `/root/m09_reader_r2`, gpt-6-luna low, fork none; packet/prompt/hashes in09-reader-round2.json. No prior feature context or coaching. Final response follows.

---

My understanding: a decorator template is a build-time rule that turns each matching source registration into a decorator definition. That definition is then applied to eligible target registrations or occurrences. The source and target are selected separately: `source_filter` filters sources, while `when` filters target occurrences. The factory gets static registration metadata, returns a `DecoratorTemplate` synchronously, and can bind a decorator dependency to the exact source registration using its ID. After a successful build, those decisions are frozen into the plan; resolution does not rerun the filters or factory.

The page presents two target-selection modes. `ServiceGroup` selects registrations that explicitly include the same group object. `DerivedServices` selects registrations by their registered service contract. Either can work with `when` for further target filtering. For generic targets, the compiler projects the target’s registered service contract onto the selector contract and specializes the decorator. Templates also participate in ordering, overlays, boundaries, lifecycle checks, inspection, and build diagnostics.

Clarity and completeness concerns:

- **Opening and first example — `decorator-templates.md`, “One source, one target.”** The example is useful, but its factory parameter is unannotated. The page later says the factory receives a frozen `RegistrationInfo`; showing an annotation or briefly naming that type here would make the callback contract clearer. The text explains that `source.id` is a registration ID, but the example does not show how to obtain other metadata or what happens if `implementation_type` is `None`.

- **Two-source example — “Two sources and selective targets.”** The assertions show both decorators’ sinks receive the input, but the example does not demonstrate how the two generated decorator layers nest or explain which layer is outermost. The later ordering section supplies that rule, though a short link or note here would help readers connect the observed event order to decorator order.

- **Filter contexts — “Two sources and selective targets.”** The distinction between a parentless canonical source component and a target occurrence in its actual parent context is precise but dense. The page says both filters are “ordinary one-argument component filters,” yet a new reader may still wonder whether `source_filter` can inspect source dependencies and whether `when` sees the target’s own ordinary dependencies. Those details are present, but spread across several sentences and would benefit from a compact contrast or example.

- **Selector semantics — “Explicit membership or registered-contract matching.”** The page explains group object identity and registered-contract matching well. “Compatible contract” and “registered service contract” remain technical terms without a small concrete example of a compatible but non-identical service type. The paragraph does clarify that inheriting implementation classes under an unrelated service contract are not selected.

- **Generic projection — “Generic identities and projection.”** The distinction among source, target, and decorator TypeVar identities is important but abstract. There is no code example showing a generic source and target with different TypeVar objects and how the factory uses `implementation_bindings(Base)`. The page also says the factory may use source bindings to choose a selector or decorator class, but does not show such a factory.

- **Ordering and overlap — “Ordering, overlap, and lifecycle.”** The nested overlay example is helpful, but “overlay-owned target,” “visible sources,” and “inherited layers” are not defined on this page. The linked [scopes.md, “ScopeBuilder overlays”](file:///var/folders/s1/8flp14pj3bv3jnzfk7_9n0lr0000gp/T/clean-ioc-m09-reader-r2-9boyg3ca/scopes.md) explains overlay ownership and anchored parent singletons, but the relationship between “layer” and source registration could still use a concise definition.

- **Editing and overlays — “Editing, overlays, and boundaries.”** The page names the patch and removal APIs but gives no code example or full registration signature. It does not specify whether a template can be patched in an overlay when inherited through a boundary, or how template IDs behave across parent and overlay plans. The page says a scope overlay can patch/remove a visible inherited template and that boundaries restrict visibility; the linked [boundaries.md, “Decorators, scope slots, and overlays”](file:///var/folders/s1/8flp14pj3bv3jnzfk7_9n0lr0000gp/T/clean-ioc-m09-reader-r2-9boyg3ca/boundaries.md) gives additional boundary context, but not template-specific examples.

- **Inspection and errors — “Inspection and errors.”** The inspection methods and broad error categories are listed, but there is no sample output or example of reading a failed decision. “Source-compilation or callback failure” and “visibility or lifespan failure” are broad categories; the page does not map individual conditions to particular diagnostic codes or show how to inspect structured diagnostics.

- **Terminology consistency.** The page uses “source registration,” “source component,” and “source” for closely related concepts, and “target registration,” “target occurrence,” and “target core.” The distinctions appear meaningful, but a short definition near the start would help. “Exact, closed `for_each` service key” is central; the page explains that open generic keys are rejected later, but does not define “closed” for a developer new to generic registrations.

- **Example prerequisites.** The examples are self-contained in imports and declarations, and the first is explicitly described as using only Clean IoC and the standard library. The page does not state the supported Python version or package installation/setup steps. I cannot tell from this packet whether those are documented elsewhere.

What I cannot determine from these pages:

- The concrete public type or import path for `RegistrationInfo`, or the exact callable typing/signature accepted for `template`.
- Whether there are additional constraints on constructing or validating a `DecoratorTemplate` beyond the fields listed.
- The precise structured diagnostic schema and which diagnostic code corresponds to each failure case.
- Whether the examples were executed successfully or what Python/package versions they require.
- The implementation behavior beyond what the public documentation states.

I reviewed only the requested documentation packet and linked pages within it; I did not inspect repository code, tests, plans, prior conversations, or external material.
