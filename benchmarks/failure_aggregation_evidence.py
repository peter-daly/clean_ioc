"""Retired failure aggregation comparison driver.

This historical experiment compared compiler switches removed by the explicit
build()/verify() API. Its recorded evidence remains in docs and .work; it is
not meaningful to rerun the old flag combinations against the current compiler.
Use the current graph_memory_evidence --operation build|verify driver for new
measurements, with performance acceptance tracked by task 25.
"""


def main():
    raise SystemExit(
        "Retired historical comparison: failure_aggregation. See docs/failure-aggregation-evidence.md; "
        "use benchmarks.graph_memory_evidence with --operation build or --operation verify."
    )


if __name__ == "__main__":
    main()
