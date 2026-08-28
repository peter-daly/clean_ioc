.PHONY: fixup lint format test docs-check ci typecheck pre-commit bench bench-save bench-compare


install-deps:
	@echo "Installing dependencies..."
	@uv sync --no-dev


install-dev-deps:
	@echo "Installing development dependencies..."
	@uv sync --all-groups


fixup:
	@echo "Fixing up..."
	@uv run ruff check . --fix
	@uv run ruff format .

typecheck:
	@echo "Typechecking"
	@uv run ty check .


pre-commit:
	@echo "Running pre-commit hooks..."
	@uv run pre-commit run --all-files


lint:
	@echo "Linting with Ruff..."
	@uv run ruff check .

format:
	@echo "Formatting with Ruff..."
	@uv run ruff format .

test:
	@echo "Running tests..."
	@uv run pytest


bench:
	@echo "Running benchmarks..."
	@uv run --group bench pytest benchmarks --benchmark-only


# Record the current revision as the baseline to compare later runs against.
bench-save:
	@echo "Saving benchmark baseline..."
	@uv run --group bench pytest benchmarks --benchmark-only \
		--benchmark-save=baseline --benchmark-save-data


# Compare against the saved baseline. Fails if any min time regresses by more
# than 50%. Only meaningful when both runs happened on the same machine.
bench-compare:
	@echo "Comparing benchmarks against baseline..."
	@uv run --group bench pytest benchmarks --benchmark-only \
		--benchmark-compare=0001_baseline --benchmark-compare-fail=min:50%

docs-check:
	@echo "Validating docs examples..."
	@uv run python scripts/validate_docs_examples.py

ci: lint format typecheck test docs-check

publish:
	@echo "Building the package..."
	@uv build
	@echo "Publishing to PyPI..."
	@uv publish --token $$PYPI_TOKEN
