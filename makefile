.PHONY: fixup lint format test ci


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

ci: lint format typecheck test

publish:
	@echo "Building the package..."
	@uv build
	@echo "Publishing to PyPI..."
	@uv publish --token $$PYPI_TOKEN