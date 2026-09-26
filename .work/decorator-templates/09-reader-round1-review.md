# Fresh reader round 1 — verbatim Phase A

Agent `/root/m09_reader_r1`, gpt-6-luna low, fork none; packet manifest/prompt in09-reader-round1.json. Reader reported only public packet access, no edits. No coaching/corrections before quiz.

---

My understanding: a decorator template is a build-time rule that enumerates registrations for one closed source service key, filters those sources, and calls a synchronous factory for each selected registration. Each factory result pairs a decorator definition with a target selector. The compiler applies it to eligible target occurrences, using `when` to filter those occurrences. The examples show how selecting the source by registration ID can wire a decorator to the exact sink registration, and how a shared `ServiceGroup` or a registered service contract can define the target set.

The examples build progressively: one source and one target selector; then multiple sources with distinct tags and selective targets. Later sections cover group membership versus contract matching, generic projection, ordering, lifecycle, overlays and boundaries, inspection, and errors. The linked pages clarify ordinary decorator ordering and filter behavior, provider-map boundaries, generic registration rules, and scope and boundary behavior.

Concerns for a developer encountering this feature for the first time:

- **The core API lacks a compact reference signature.** The opening describes a `DecoratorTemplate` as a decorator, selector, and ordinary options, but readers must infer the accepted fields from the example and the sentence listing them in “One source, one target.” The registration and patch methods are also shown with `...`, without a full signature or defaults. A small API summary would help establish required fields, optional fields, and accepted selector forms. [Decorator templates, “One source, one target” and “Editing, overlays, and boundaries”]

- **“Exact, closed” is central but still takes effort to parse.** The generic section clarifies that `for_each` must be a closed source service key, and that the factory receives that key as `source.service_type`; it does not explain in a simple example what happens if a registration is registered under a base service or if multiple closed keys are relevant. The restrictions are clear in principle, but the selection boundary could be made more concrete. [Decorator templates, opening and “Generic identities and projection”]

- **The two filters are easy to conflate.** The page says `source_filter` sees a canonical, parentless component and `when` sees target occurrences in parent context. The distinction is important, but readers have to hold several terms in mind—canonical source, occurrence, parent context, recursively excluded decorators—to follow the behavior. A short “source vs target” comparison or diagram could make this clearer. [Decorator templates, “Two sources and selective targets”; component-filter details in “Component filtering,” “Decorator selection sees the undecorated core,” and “Composing filters”]

- **Some metadata wording is undefined at the point of use.** “Retains its ordinary dependency/build context” and “visible registration declaration order (and overlay precedence)” are not spelled out with a concrete example. “Visible” is discussed later for boundaries, and overlay plans are discussed in the linked scopes page, but the precedence between inherited and overlay source registrations remains hard to predict from the template page alone. [Decorator templates, “Two sources and selective targets,” “Ordering, overlap, and lifecycle,” and “Editing, overlays, and boundaries”; scopes page, “ScopeBuilder overlays”]

- **`ServiceGroup` versus `DerivedServices` is explained well but could use a quick decision cue.** The section gives a detailed comparison, including the “ungrouped” example. A short rule of thumb—use a group for explicit opt-in membership, use `DerivedServices` for matching registered contracts—would make this distinction easier to retain. [Decorator templates, “Explicit membership or registered-contract matching”]

- **The generic projection section is dense for a feature overview.** It introduces source implementation bindings, target registered-contract projection, separate TypeVar identities, aliases, and ambiguous projections. These are meaningful constraints, but there is no runnable generic example to show how a factory would use `implementation_bindings()` or how target specialization behaves. [Decorator templates, “Generic identities and projection”; linked generics page, “Generic decorators”]

- **Failure descriptions do not tell a reader what to inspect first.** The page lists diagnostic categories, but does not show a representative error or indicate where the structured diagnostic fields can be found. `explain_template_sources()` and `explain_decorators()` are named, but their return shapes or a short sample are absent. The value-free inspection limitation is clear. [Decorator templates, “Inspection and errors”]

What I could not determine from the packet pages:

- The complete Python signatures and defaults for `DecoratorTemplate`, `register_decorator_template()`, `patch_decorator_template()`, `explain_template_sources()`, and the template-related fields of `explain_decorators()`.
- The precise source-order precedence when overlay and inherited registrations are both visible.
- A concrete generic template example demonstrating source binding and target projection.
- The exact structured fields and presentation of a template compilation diagnostic.
