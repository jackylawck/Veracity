.PHONY: install test ingest-dryrun ingest check-schema clean

VENV := venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.in

test:
	$(PYTHON) -m pytest -v tests/

check-schema:
	$(PYTHON) -c "import json, jsonschema; schema=json.load(open('schemas/record.schema.json')); data=json.load(open('public/api/records-latest.json')); [jsonschema.validate(instance=r, schema=schema) for r in data['records']]; print('Schema validation passed: All records adhere to Schema v2.0.0!')"

ingest-dryrun:
	$(PYTHON) -m scripts.ingest --dry-run

ingest:
	$(PYTHON) -m scripts.ingest

clean:
	rm -rf __pycache__ .pytest_cache tests/__pycache__ adapters/__pycache__ scripts/__pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} +
