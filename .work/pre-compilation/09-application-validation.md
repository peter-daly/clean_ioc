# 09 — Application equivalence and deployment measurements

Created: 2026-10-09\
Status: Not ready — application, target environment and criteria need selection\
Assignment: Unassigned\
Prerequisites: Task 02's agreed subset; implementations from the applicable tasks

## Outcome

Establish that a representative application can use precompilation with equivalent
resolution behaviour and a useful startup-memory benefit. Keep the existing
synthetic fixture as a controlled baseline, then measure the selected application
in a production-like local deployment environment.

## Readiness and input needed

- Select an application composition and revision, its required features and its
  reproducible local dependencies. Data-protection-cop or Polaris may inform the
  choice, but neither is assumed to be approved or available for this task.
- Choose the target Linux/x86 image, Python/dependency versions, process layout
  (including worker count/preload), CPU/memory limits and readiness definition.
- Decide representative first-request and steady-state work, including lazy
  resolutions that low traffic might otherwise leave unexercised.
- Agree acceptance criteria for behaviour, load/readiness time, peak/current
  memory, artifact size and allowed optional-feature overhead. Do not invent a
  production memory target from the synthetic result.

Select the application early so it informs task 02. Execution waits for the
relevant feature implementations and reproducible target environment. This task
does not authorize production restarts, deployments or other service mutations.

## Work

1. Capture an ordinary-compile baseline at the same source/dependency revision
   and with the same metadata, profiling, environment values and workload as the
   artifact case. Record the exact image/platform and application layout.
2. Run compilation/export and loading in separate fresh processes. Reuse the
   existing rich fixture, add approved slots/features, and preserve prior raw
   evidence. Keep timed and allocation-traced runs separate.
3. Validate the application composition's results and lifetimes: singleton,
   scoped, per-resolution and transient sharing; decorators; providers/maps;
   collections; startup inputs; pre-configurations; warmup; resource cleanup.
   Include expected failures and cancellation where supported.
4. Test loading twice in one process and loading across fresh processes, proving
   fresh runtime state and stable application binding/type semantics. Guard
   compiler and build-callback entry points during loading and ordinary startup.
5. Exercise missing symbols, incompatible code/dependencies, incomplete artifacts,
   unsupported features and missing bindings. Verify clear failures without
   activating the application or silently compiling a replacement graph.
6. Measure imports, load, provisioning, warmup/readiness, first resolution and
   steady-state work separately. Record artifact size, process RSS/peak,
   retained/traced Python memory and container/cgroup usage where available.
7. For Docker results, identify metric definitions, aggregate all application
   processes and record anonymous/file-backed/kernel memory plus limit/OOM events
   where available. Sampled usage and kernel-recorded peaks are distinct. Report
   file-cache conditions and do not equate process RSS with Datadog/container data.
8. Use repeated runs with balanced/interleaved order where practical, no competing
   benchmarks, and recorded cache/host conditions. State sample counts, spread
   and measurement limitations instead of treating a single run as a guarantee.

## Verification and acceptance

- [ ] The selected composition, image, workload and acceptance criteria are
  recorded before measurements begin.
- [ ] Normal and loaded containers match supported behaviour and failure/cleanup
  semantics; no application graph compilation occurs in the load process.
- [ ] Independent loads do not share mutable runtime state or supplied objects.
- [ ] A repeatable local runner and raw evidence reproduce both synthetic and
  application comparisons using the same inputs/options within each comparison.
- [ ] The report separates compilation cost, import cost, artifact preparation,
  activation cost and process/container memory; it states unsupported features
  and extrapolation limits.
- [ ] Applicable repository checks pass for implemented changes. The final report
  recommends retain, revise or defer precompilation against the agreed criteria;
  completing a measurement alone does not establish production readiness.

## Starting points

- [Artifact tests](../../tests/test_graph_artifact_experiment.py),
  [rich fixture](../../benchmarks/graph_memory_fixture.py) and
  [memory evidence runner](../../benchmarks/graph_memory_evidence.py).
- [Existing retest and caveats](../graph-memory-optimization/artifact-retest-post05.md)
  and [experiment documentation](../../docs/graph-artifact-experiment.md).
- [Feature coverage task](02-feature-coverage.md) and
  [shared acceptance rules](README.md).
