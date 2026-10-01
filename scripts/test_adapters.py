#!/usr/bin/env python
"""Tests each adapter in the registry: loading, weight identity and one prediction.

Usage: HF_HUB_CACHE=<cache> .venv/bin/python scripts/test_adapters.py [model ...]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from service.backends import build_backend          # noqa: E402
from service.config import load_config              # noqa: E402

TEXTS = [
    ("positive", "I love this product, it changed my life!"),
    ("negative", "El producto llegó roto y nadie responde. Una estafa."),
]

cfg = load_config()
targets = sys.argv[1:] or list(cfg.models)
print(f"active model in config: {cfg.active}\n")

for mid in targets:
    spec = cfg.spec(mid)
    print(f"=== {mid}  (adapter: {spec.adapter}, supports: {sorted(spec.supports)})")
    try:
        backend = build_backend(spec)
        backend.load()
    except Exception as exc:  # noqa: BLE001
        print(f"  LOAD FAILED: {type(exc).__name__}: {exc}\n")
        continue
    w = backend.weights_info()
    print(f"  weights: {str(w.get('sha256'))[:16]}… expected: {str(w.get('expected'))[:16]}… "
          f"matches: {w.get('match')}  [{w.get('note')}]")
    q = [{"id": "s", "type": "noul", "instructions": "Does this text express positive sentiment?",
          "options": [], "scale": []}]
    for label, text in TEXTS:
        try:
            item = backend.predict(text, q)["s"]
            p = item["probs"][1] if item.get("probs") else float("nan")
            verdict = "POSITIVE" if item.get("value") else "NEGATIVE"
            print(f"  {label:9s} -> {verdict:8s} P(positive)={p:.4f}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {label:9s} -> ERROR {type(exc).__name__}: {exc}")
    print()
