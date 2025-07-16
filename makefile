.PHONY: fixup lint format test ci


fixup:
	@echo "Fixing up..."
	@uv ruff check . --fix
	@uv ruff format .

typecheck:
	@echo "Typechecking"
	@uv pyright .


lint:
	@echo "Linting with Ruff..."
	@uv ruff check .

format:
	@echo "Formatting with Ruff..."
	@uv ruff format .

test:
	@echo "Running tests..."
	@uv pytest .

ci: lint format typecheck test

publish:
	@echo "Building the package..."
	@uv build
	@echo "Publishing to PyPI..."
	@uv publish --token $$PYPI_TOKEN