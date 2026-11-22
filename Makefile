.PHONY: test-fast test-all test-e2e test-perf lint type-check security coverage

test-fast:
	python -m pytest -m "unit or api or security"

test-all:
	python -m pytest --cov=app --cov-branch --cov-report=term-missing --cov-report=html

test-e2e:
	python -m pytest -m e2e

test-perf:
	python -m pytest -m performance --benchmark-columns=mean,min,max

lint:
	ruff check app tests
	ruff format --check app tests
	python -m pytest tests/accessibility/test_accessibility.py::test_every_form_input_has_an_associated_label_and_headings_are_structured

type-check:
	mypy --strict app

security:
	bandit -r app
	pip-audit -r requirements.txt --no-deps
	detect-secrets scan app tests static docs README.md requirements.txt requirements-dev.txt

coverage:
	python -m pytest --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=90
