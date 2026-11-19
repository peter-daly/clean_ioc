# M09 round 1 examiner questions — full original wording

Examiner `/root/m09_review`, gpt-6-astra high. Supplied after neutral Phase A and before Phase B. Preserved from the original examiner response. Frozen rubric: all ten questions, Q1–Q7 critical, at least 18/20, Q1–Q7 full marks, no zero scores, and no substantiated core documentation gap.

---

Answer using only the public documentation packet. Cite the supporting page and section for each answer, and state explicitly when the documentation does not establish an answer.

1. Two `TelemetrySink` registrations use the same `BufferedSink` implementation but different configurations. Each selected registration should produce a `MeasuredJob` decorator around eligible `Job` targets. What does the template factory receive and return? Show the smallest template configuration that binds each decorator’s `sink` argument to its own source registration. Does enumerating sources construct them?

2. Only sinks tagged `location="remote"` should produce decorators, and only jobs with an ordinary descendant tagged `needs="telemetry"` should receive them. Show where both restrictions belong. Describe the component, parent context, and dependency graph available to each predicate, including whether decorator-added dependencies are visible.

3. Two registrations of `Job` use the same compatible implementation, but only one joins `ServiceGroup("measured", service_type=Job)`. Which can this group select? How would `DerivedServices(Job)` change eligibility? Consider also a compatible implementation registered under an unrelated service contract. What registrations or memberships does the automatic selector create?

4. A registration bundle and a policy bundle each construct their own `ServiceGroup("measured", service_type=Job)`. Will the policy select the registration bundle’s members? Show how you would arrange the declarations across modules. Are contribution keys required, and what can application code resolve from the group?

5. A template is declared before a deferred subclass-discovery rule. Later, a `CompressJob` subclass becomes available before `build()`. Show a discovery declaration that makes discovered registrations join an explicit group. Can either target selector perform that discovery itself? What happens if `CompressJob` becomes available only after a successful build?

6. A source implementation inherits `ArchiveBackend[Document]`; targets are requested as closed specializations of `Task[Request, Result]`. Explain how a factory can inspect the source specialization and how the compiler determines the target specialization. Address distinct TypeVar objects with the same name, an originally requested closed alias, unknown source implementation metadata, and ambiguous target projection.

7. Two registrations of `ArchiveBackend` have different settings and correspond to resource labels `"cold"` and `"hot"`. A job’s ordinary dependency graph reaches `"cold"` resources through three paths and contains no `"hot"` resource. Explain how to configure exact source binding and source-dependent target applicability. How many layers should that template add to this target occurrence, and what if its exact selected source cannot satisfy the dependency at the injection point?

8. Three applicable definitions are declared in this order: `OuterTrace` at position `10`, `Checksum` at position `-2`, and `Timing` at position `10`. Predict their outside-to-inside order. Separately, what happens when two distinct templates choose the same source and target? Can a dependency introduced only by one decorator make another template’s target predicate match?

9. A built parent container has a singleton job and a template. Compare a plain child scope with an overlay that adds a source and a new eligible job. Which plans can acquire new layers? Explain whether a shared group grants access to private boundary registrations or lets the overlay change the parent singleton’s composition. When may factories and filters run again?

10. Write a small, complete program using newly invented local types that decorates a target through either explicit group membership or automatic selection. Include a source filter, an exact source argument binding, a target `when`, and an assertion demonstrating the result. Show the changes needed to use the other target-selection form, and identify any API detail needed for your program that you could not establish from the packet.
