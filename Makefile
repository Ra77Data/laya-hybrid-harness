# Atajos del harness. `make` sin argumentos lista lo disponible.
.DEFAULT_GOAL := help
SHELL := /bin/bash
UV ?= $(shell command -v uv 2>/dev/null)
PY := .venv/bin/python
PORT ?= 8090

.PHONY: help setup setup-full serve demo test smoke metrics report cordis clean

help:  ## Muestra esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup:  ## Crea el entorno e instala el camino del demo (transformers; cualquier SO)
	@if [ -n "$(UV)" ]; then \
		uv venv --python 3.11 .venv && uv pip install --python $(PY) -e ".[demo]"; \
	else \
		python3 -m venv .venv && $(PY) -m pip install -U pip && $(PY) -m pip install -e ".[demo]"; \
	fi
	@echo "listo. Ahora: make demo"

setup-full:  ## Igual que setup, más los adaptadores de Laya (CoreML: macOS Apple Silicon)
	@if [ -n "$(UV)" ]; then \
		uv venv --python 3.11 .venv && uv pip install --python $(PY) -e ".[full]"; \
	else \
		python3 -m venv .venv && $(PY) -m pip install -U pip && $(PY) -m pip install -e ".[full]"; \
	fi

config:  ## Crea config.yaml desde la plantilla si no existe
	@[ -f config.yaml ] || (cp config.example.yaml config.yaml && echo "creado config.yaml desde config.example.yaml (editá las rutas marcadas EDITAR)")

serve: config  ## Arranca el servicio en primer plano
	LAYA_PORT=$(PORT) $(PY) -m uvicorn service.server:app --host 127.0.0.1 --port $(PORT)

demo:  ## Demostración completa de un comando: arranca, muestra casos y métricas, apaga
	bash scripts/demo.sh

smoke:  ## Verifica que el servicio responde y con qué modelo
	@curl -s "http://127.0.0.1:$(PORT)/health" | $(PY) -m json.tool || \
		(echo "el servicio no responde en $(PORT); probá 'make serve'"; exit 1)

metrics:  ## Métricas del tráfico registrado (por defecto 24 h)
	@curl -s "http://127.0.0.1:$(PORT)/metrics?hours=24" | $(PY) -m json.tool

report:  ## Informe legible del tráfico registrado
	$(PY) scripts/report_decisions.py --hours 24

test: config  ## Self-test del servicio y sondas de robustez y concurrencia
	bash scripts/run_tests.sh

cordis:  ## Genera el plugin de DSH con la ruta absoluta de este repo
	@sed "s|__HARNESS_DIR__|$$(pwd)|" dsh-laya-plugin/laya.cordis.yml.example > dsh-laya-plugin/laya.cordis.yml
	@echo "escrito dsh-laya-plugin/laya.cordis.yml -> $$(pwd)/dsh-laya-plugin/laya-decide.plugin.mjs"

clean:  ## Borra el entorno y los artefactos locales
	rm -rf .venv .uvcache logs results/*.jsonl
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
