PY := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

POLICY_PATH ?= policy/standard.yaml
SIGNATURES_PATH ?= signatures.json
DATA_DIR ?= data

export POLICY_PATH
export SIGNATURES_PATH
export DATA_DIR

.PHONY: run test demo

demo:
	$(PY) demo/run.py

run:
	$(PY) -m uvicorn control.app:app --host 127.0.0.1 --port 8000 --app-dir src

test:
	$(PY) -m pytest tests/test_controls.py -q
