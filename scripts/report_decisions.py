#!/usr/bin/env python
"""Informe del tráfico real registrado por el servicio.

Uso:
  python scripts/report_decisions.py [--hours 24] [--top 8]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from service.config import load_config          # noqa: E402
from service.observability import DecisionLog   # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--hours", type=float, default=24)
ap.add_argument("--config", default=None)
args = ap.parse_args()

cfg = load_config(args.config)
o = cfg.observability
log = DecisionLog(enabled=o.get("enabled", True), directory=o.get("directory", "logs/decisions"),
                  level=o.get("level", "excerpt"), window=int(o.get("window", 5000)),
                  retain_days=int(o.get("retain_days", 30)))
m = log.metrics(hours=args.hours)

print(f"=== decisiones de las últimas {args.hours} h")
if not m["requests"]:
    print("  (no hay registros todavía)")
    raise SystemExit(0)

print(f"  peticiones {m['requests']} | respuestas {m['answers']} | "
      f"derivadas {m['answers_delegated']} ({m['delegation_rate']*100:.1f} %)")
print(f"  modelos que contestaron: {m['models_seen']}")
print(f"  idioma (heurística): {m['languages']}")
print(f"  largo del texto: p50 {m['chars']['p50']} | p95 {m['chars']['p95']} caracteres")
print(f"  latencia: p50 {m['latency_ms']['p50']} | p90 {m['latency_ms']['p90']} | "
      f"p95 {m['latency_ms']['p95']} | max {m['latency_ms']['max']} ms")
print(f"  truncados {m['truncated']} | sin calibrar {m['uncalibrated']} | no soportados {m['unsupported']}")

print("\n  por primitiva:")
for t, v in m["by_type"].items():
    print(f"    {t:7s} {v['answers']:5d} respuestas | deriva {v['delegation_rate']*100:5.1f} % | "
          f"confianza media {v['mean_confidence']:.3f}")

print("\n  por qué se derivó:")
for k, v in sorted(m["delegate_kinds"].items(), key=lambda x: -x[1]):
    print(f"    {k:38s} {v:5d}")

print("\n  histograma de confianza:")
for k, v in m["confidence_hist"].items():
    print(f"    {k:14s} {v:5d}  {'#' * min(60, v)}")

print("\n  histograma de masa neutral (para recalibrar el umbral con tráfico propio):")
for k, v in m["neutral_mass_hist"].items():
    print(f"    {k:14s} {v:5d}  {'#' * min(60, v)}")

print(f"\n  registro: nivel={m['log']['level']} dir={m['log']['directory']} "
      f"archivos={m['log']['files']} escritos={m['log']['written']} errores={m['log']['errors']}")
