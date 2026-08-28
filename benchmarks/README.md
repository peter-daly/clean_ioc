# Benchmarks

Resolution benchmarks for the container, built with
[pytest-benchmark](https://pytest-benchmark.readthedocs.io/).

They are not part of the test suite. `make test` and `make ci` do not run them,
and `pytest` alone does not collect them, because `testpaths` is set to `tests`.

## Running them

```bash
make bench           # run every benchmark and print the table
make bench-save      # record the current revision as the baseline
make bench-compare   # run again and fail if anything regressed by over 50%
```

The usual loop for a performance change is `make bench-save` on a clean tree,
then the change, then `make bench-compare`.

## What each benchmark isolates

Every benchmark registers its graph outside the measured callable, so the
numbers cover resolution only. The one exception is
`test_registration_of_many_types`, which measures registration on purpose:
work moved out of the resolve path has to land somewhere, and that is where.

| Group | Benchmark | Isolates |
| --- | --- | --- |
| `single` | `test_transient_with_no_dependencies` | The floor of the resolve path |
| `single` | `test_singleton_already_cached` | A warm cache hit, so mostly registration lookup |
| `shape` | `test_deep_transient_graph` | Cost that scales with graph depth |
| `shape` | `test_wide_transient_graph` | Cost that scales with node count |
| `shape` | `test_collection_dependency` | `list[T]` resolution over many registrations |
| `lookup` | `test_filtered_lookup_over_many_registrations` | The registration scan and the filter call per candidate |
| `lookup` | `test_decorator_chain` | The decorator scan and the extra node per decorator |
| `scope` | `test_scoped_resolve_in_root_scope` | Baseline for the scoped path |
| `scope` | `test_scoped_resolve_in_nested_scope` | The added cost of scope nesting |
| `async` | `test_async_deep_transient_graph` | The separate async resolve path |
| `registration` | `test_registration_of_many_types` | Constructor introspection at registration |

Graph shapes are generated in `graphs.py` rather than written out, so depth and
width are parameters instead of constants. The generated classes are real
classes with real `__init__` signatures, so the container introspects them
exactly as it would introspect application code.

## Reading the numbers

Compare like with like:

- **Only compare runs from the same machine.** Absolute times mean nothing
  across machines, and the CI job exists to compare two revisions on one runner,
  not to publish a number.
- **Prefer `min` over `mean`.** `min` is the least sensitive to scheduling noise.
  Both `make bench-compare` and the CI job use it.
- **Async numbers stand apart.** They include a fixed `run_until_complete`
  overhead, so compare them only to other async runs.

## In CI

`.github/workflows/benchmarks.yml` runs on every pull request. It measures the
merge base and the pull request head on the same runner, using the benchmark
code from the pull request for both, so the only difference between the two runs
is library code. It fails if any `min` time regresses by more than 50%.

That threshold is loose on purpose. The job is a guard against a change that
makes resolution much slower. Small differences are noise on a shared runner and
belong in a local `make bench-compare`.
