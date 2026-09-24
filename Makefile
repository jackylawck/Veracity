.PHONY: install test ingest-dryrun ingest check-schema clean

# 動態判斷 Python 直譯器：優先使用虛擬環境，若不存在則回退到系統環境
PYTHON := $(shell if [ -f venv/bin/python ]; then echo venv/bin/python; else echo python3; fi)
PIP := $(shell if [ -f venv/bin/pip ]; then echo venv/bin/pip; else echo pip; fi)

install:
	$(PYTHON) -m venv venv
	venv/bin/pip install --upgrade pip
	venv/bin/pip install --require-hashes -r requirements.lock

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
