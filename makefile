.PHONY: fixup lint format test docs-check benchmark benchmark-check ci typecheck pre-commit


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
	@echo "Checking formatting with Ruff..."
	@uv run ruff format --check .

test:
	@echo "Running tests..."
	@uv run pytest .

docs-check:
	@echo "Validating docs examples..."
	@uv run python scripts/validate_docs_examples.py

benchmark:
	@echo "Running BenchBro benchmarks..."
	@uv run benchbro run

benchmark-check:
	@echo "Checking BenchBro discovery..."
	@uv run benchbro list --verbose

ci: lint format typecheck test docs-check benchmark-check

publish:
	@echo "Building the package..."
	@uv build
	@echo "Publishing to PyPI..."
	@uv publish --token $$PYPI_TOKEN
