"""Retired frozen draft capacity comparison driver.

This historical experiment compared compiler switches removed by the explicit
build()/analyse() API. Its recorded evidence remains in docs and .work; it is
not meaningful to rerun the old flag combinations against the current compiler.
Use the current graph_memory_evidence --operation build|analyse driver for new
measurements, with performance acceptance tracked by task 25.
"""


def main():
    raise SystemExit(
        "Retired historical comparison: frozen_draft_capacity. See docs/frozen-draft-capacity-evidence.md; "
        "use benchmarks.graph_memory_evidence with --operation build or --operation analyse."
    )


if __name__ == "__main__":
    main()
