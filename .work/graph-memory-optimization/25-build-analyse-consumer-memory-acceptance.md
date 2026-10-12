# 25 — Verify the whole upgrade against the consumer baseline

Created: 2026-10-10\
Status: Ready for assignment — tasks 20–24 integrated; preserved baselines available; performance measurements not started\
Assignment: Unassigned\
Recommended reasoning effort: High (`high`)\
Prerequisites: [Investigation](build-and-analyse-investigation.md), task 18 and actual consumer evidence

## Outcome

Establish whether execution-only build fixes the real Cop regression. Include the
entire API/policy change in the comparison; do not choose a baseline after an
expensive policy was already introduced. The maintainer has deferred further
memory and timing measurements until tasks 20–24 are integrated. Preserve source,
environment snapshots and samples already collected during task 20; they are
inputs to the final comparison, not a reason to repeat benchmarks at each step.
Correctness and quality checks continue throughout implementation.

## Baselines and attribution

Preserve exact source/environment identity and runnable isolated copies for:

1. Previous consumer local validation fix, compiler SHA
   `6253f5e38bd8819099db53514ede0d3c0efc4f451b3ea33f05c6e4a9932e4253`.
2. Tasks 10/11 source, before task 12, compiler SHA
   `4a6c447812f7b313b96d2ce3bf09aab54207f24d88764b830a4c24010be5b683`.
3. Current regressed compiler, SHA
   `1a60386b392058ac47143b3acf4fc82b1034b95f360854dae2e98ff6cde42223`.
4. The final integrated `build()`/`analyse()` source, with exact measured hashes;
   preserve intermediate task source identities without benchmarking each step.

Use matching component/supporting source captures as well as container.py. The
package version label alone identifies none of these states. The task 20 source
and environment snapshots preserve the pre-change versions. Keep them intact;
never reset the maintainer's dirty checkout to run an old version. Any further
baseline samples or attribution measurements run in the final measurement phase,
using isolated preserved source, rather than blocking ongoing implementation.
Temporary attribution controls may vary internal capture while preserving actual
rule registration, but are not public APIs or substitutes for complete analysis.

## Protocol

- Run this measurement protocol after compiler and consumer migration tasks
  20–24 are integrated. Do not require before/after benchmark runs for each task.
  Preserve completed baseline samples; decide any matched remeasurement needs
  against the final environment during this task.
- Actual Cop API/worker with both real UoW rules registered. New build is expected
  to invoke zero rules; analyse must run both. Other wiring inputs/provider roots
  stay matched. Run full analysis separately from startup, reporting its total cost.
- Start with at least three fresh serial untraced and three separately traced
  native processes per main policy. Counterbalance policy order, keep dependencies,
  Python and architecture fixed, and record prebuild RSS, build time, peak RSS,
  settled RSS, traced peak and retained allocations independently.
- Linux Docker: same image base/support packages, Gunicorn/config/workload, Python
  3.14.4 ARM64, 500m CPU, 512 MiB and no swap for the initial comparison. Repeat
  containers to obtain ranges; do not promote one readiness sample to a distribution.
- Record raw cgroup total, anonymous/file/kernel breakdown, Docker displayed metric,
  kernel peak, readiness and a consistent 60-second post-readiness interval. Report
  helper/profiler overhead. File-cache differences cannot count as compiler savings.
- Trace imports, declaration/composition, selection, instruction emission/freezing
  and post-GC retention separately where possible. Phase observers and constructor
  censuses run outside timing samples and their maxima are never summed.
- Preserve the rich repeated synthetic fixture, low-definition-reuse control,
  providers/maps, saved callback snapshots, warmups and instrumented builds. Recheck
  cold/steady resolution and analysis inspection costs, not startup alone.
- Measure optional composition unrequested, held and released, and a retained
  consumed builder/boundary handle. Separate actual reference release from merely
  moving declarations outside the runtime. Include declaration/transfer/freeze
  overlap; single-attempt consumption is not itself a measured peak-memory win.
- Fresh baseline/after samples use safe output directories. Existing consumer and
  task 18 evidence remains immutable. No concurrent tests during benchmark windows.

## Acceptance

- Report total old-consumer→final change as well as current→final and individual
  attribution. If previous consumer memory/time is not recovered, identify and
  explicitly review the remaining regression; do not declare success from a smaller
  retained heap, a synthetic improvement, or lower file-cache accounting.
- Demonstrate absent validators/report/inspection allocation in build, including
  with rules registered and optional warmup/instrumentation enabled.
- Discovery, actual dispatch, cleanup and unchanged capacity limits pass. Invalid
  policy cases are rejected by analyse, with zero build-rule invocation as intended.
- No unexplained lost callbacks, added public roots, weakened application workloads
  or raised resource limits. Record analysis cost and intentional checking behavior
  separately from execution equivalence.
- A final keep/refine/drop decision, complete reproduction identity, raw ranges,
  test results, consumer migration patch and explicit remaining limitations.

Native ARM/Docker results do not establish production x86 memory. Release and
deployment remain separate work. No measurement or implementation is performed
merely by creating this planning item.
