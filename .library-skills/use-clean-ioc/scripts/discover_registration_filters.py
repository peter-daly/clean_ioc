#!/usr/bin/env python3
"""Discover registration filters exposed by the installed Clean IoC version."""

from __future__ import annotations

import argparse
import inspect

import clean_ioc.registration_filters as registration_filters


def _matches_search(name: str, signature: str, docstring: str, terms: list[str]) -> bool:
    searchable = f"{name} {signature} {docstring}".lower()
    return all(term.lower() in searchable for term in terms)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "terms",
        nargs="*",
        help="Case-insensitive terms that must occur in the name, signature, or docstring.",
    )
    parser.add_argument("--full", action="store_true", help="Print complete docstrings.")
    args = parser.parse_args()

    matches = []
    for name in registration_filters.__all__:
        registration_filter = getattr(registration_filters, name)
        signature = str(inspect.signature(registration_filter))
        docstring = inspect.getdoc(registration_filter) or ""
        if _matches_search(name, signature, docstring, args.terms):
            matches.append((name, signature, docstring))

    if not matches:
        print("No registration filters matched the search terms.")
        return 1

    for index, (name, signature, docstring) in enumerate(matches):
        if index:
            print()
        print(f"{name}{signature}")
        if args.full:
            print(docstring)
        else:
            summary = docstring.splitlines()[0] if docstring else "No docstring available."
            print(f"  {summary}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
