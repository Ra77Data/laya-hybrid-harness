#!/usr/bin/env python
"""Prueba cada adaptador del registro: carga, identidad de pesos y una predicción.

Uso: HF_HUB_CACHE=<cache> .venv/bin/python scripts/test_adapters.py [modelo ...]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from service.backends import build_backend          # noqa: E402
from service.config import load_config              # noqa: E402

TEXTS = [
    ("positivo", "I love this product, it changed my life!"),
    ("negativo", "El producto llegó roto y nadie responde. Una estafa."),
]

cfg = load_config()
targets = sys.argv[1:] or list(cfg.models)
print(f"modelo activo en config: {cfg.active}\n")

for mid in targets:
    spec = cfg.spec(mid)
    print(f"=== {mid}  (adaptador: {spec.adapter}, soporta: {sorted(spec.supports)})")
    try:
        backend = build_backend(spec)
        backend.load()
    except Exception as exc:  # noqa: BLE001
        print(f"  CARGA FALLÓ: {type(exc).__name__}: {exc}\n")
        continue
    w = backend.weights_info()
    print(f"  pesos: {str(w.get('sha256'))[:16]}… esperado: {str(w.get('expected'))[:16]}… "
          f"coincide: {w.get('match')}  [{w.get('note')}]")
    q = [{"id": "s", "type": "noul", "instructions": "Does this text express positive sentiment?",
          "options": [], "scale": []}]
    for label, text in TEXTS:
        try:
            item = backend.predict(text, q)["s"]
            p = item["probs"][1] if item.get("probs") else float("nan")
            trato = "POSITIVO" if item.get("value") else "NEGATIVO"
            print(f"  {label:9s} -> {trato:8s} P(positivo)={p:.4f}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {label:9s} -> ERROR {type(exc).__name__}: {exc}")
    print()
