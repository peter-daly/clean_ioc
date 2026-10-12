"""Discover public Clean IoC component filters by name and documentation."""

from __future__ import annotations

import argparse
import inspect

import clean_ioc.component_filters as component_filters


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("terms", nargs="*")
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    terms = tuple(term.lower() for term in args.terms)

    for name in component_filters.__all__:
        subject = getattr(component_filters, name)
        signature = str(inspect.signature(subject)) if callable(subject) else ""
        documentation = inspect.getdoc(subject) or ""
        haystack = f"{name} {signature} {documentation}".lower()
        if not all(term in haystack for term in terms):
            continue
        print(f"{name}{signature}")
        if args.full and documentation:
            print(f"  {documentation.replace(chr(10), chr(10) + '  ')}")


if __name__ == "__main__":
    main()
