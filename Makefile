# Harness shortcuts. `make` with no arguments lists what is available.
.DEFAULT_GOAL := help
SHELL := /bin/bash
UV ?= $(shell command -v uv 2>/dev/null)
PY := .venv/bin/python
PORT ?= 8090

.PHONY: help setup setup-full serve demo test smoke metrics report cordis clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup:  ## Create the environment and install the demo path (transformers; any OS)
	@if [ -n "$(UV)" ]; then \
		uv venv --python 3.11 .venv && uv pip install --python $(PY) -e ".[demo]"; \
	else \
		python3 -m venv .venv && $(PY) -m pip install -U pip && $(PY) -m pip install -e ".[demo]"; \
	fi
	@echo "listo. Ahora: make demo"

setup-full:  ## Same as setup, plus the Laya adapters (CoreML: macOS Apple Silicon)
	@if [ -n "$(UV)" ]; then \
		uv venv --python 3.11 .venv && uv pip install --python $(PY) -e ".[full]"; \
	else \
		python3 -m venv .venv && $(PY) -m pip install -U pip && $(PY) -m pip install -e ".[full]"; \
	fi

config:  ## Create config.yaml from the template if it does not exist
	@[ -f config.yaml ] || (cp config.example.yaml config.yaml && echo "creado config.yaml desde config.example.yaml (editá las rutas marcadas EDITAR)")

serve: config  ## Start the service in the foreground
	LAYA_PORT=$(PORT) $(PY) -m uvicorn service.server:app --host 127.0.0.1 --port $(PORT)

demo:  ## Whole demonstration in one command: starts, shows cases and metrics, shuts down
	bash scripts/demo.sh

smoke:  ## Check that the service answers and with which model
	@curl -s "http://127.0.0.1:$(PORT)/health" | $(PY) -m json.tool || \
		(echo "el servicio no responde en $(PORT); probá 'make serve'"; exit 1)

metrics:  ## Metrics for the logged traffic (24 h by default)
	@curl -s "http://127.0.0.1:$(PORT)/metrics?hours=24" | $(PY) -m json.tool

report:  ## Readable report of the logged traffic
	$(PY) scripts/report_decisions.py --hours 24

test: config  ## Service self-test and robustness and concurrency probes
	bash scripts/run_tests.sh

cordis:  ## Generate the DSH plugin with this repo's absolute path
	@sed "s|__HARNESS_DIR__|$$(pwd)|" dsh-laya-plugin/laya.cordis.yml.example > dsh-laya-plugin/laya.cordis.yml
	@echo "escrito dsh-laya-plugin/laya.cordis.yml -> $$(pwd)/dsh-laya-plugin/laya-decide.plugin.mjs"

clean:  ## Delete the environment and local artifacts
	rm -rf .venv .uvcache logs results/*.jsonl
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
