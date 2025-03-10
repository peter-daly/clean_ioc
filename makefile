.PHONY: fixup lint format test ci


fixup:
	@echo "Fixing up..."
	@poetry run ruff check . --fix
	@poetry run ruff format .
	
typecheck:
	@echo "Typechecking"
	@poetry run pyright .


lint:
	@echo "Linting with Ruff..."
	@poetry run ruff check .

format:
	@echo "Formatting with Ruff..."
	@poetry run ruff format .

test:
	@echo "Running tests..."
	@poetry run pytest .

ci: lint format typecheck test

publish:
	@echo "Publishing to PyPI..."
	@poetry publish --build --username __token__ --password $PYPI_TOKEN