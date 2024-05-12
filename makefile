.PHONY: lint format test ci

typecheck:
	@echo "Typechecking"
	@poetry run ruff check .


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