.PHONY: fixup lint format test docs-check ci


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
	@uv run pyright .


lint:
	@echo "Linting with Ruff..."
	@uv run ruff check .

format:
	@echo "Formatting with Ruff..."
	@uv run ruff format .

test:
	@echo "Running tests..."
	@uv run pytest .

docs-check:
	@echo "Validating docs examples..."
	@uv run python scripts/validate_docs_examples.py

ci: lint format typecheck test docs-check

publish:
	@echo "Building the package..."
	@uv build
	@echo "Publishing to PyPI..."
	@uv publish --token $$PYPI_TOKEN
