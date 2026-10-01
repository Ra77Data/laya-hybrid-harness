#!/usr/bin/env python
"""Report on the real traffic logged by the service.

Usage:
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

print(f"=== decisions over the last {args.hours} h")
if not m["requests"]:
    print("  (no records yet)")
    raise SystemExit(0)

print(f"  requests {m['requests']} | answers {m['answers']} | "
      f"delegated {m['answers_delegated']} ({m['delegation_rate']*100:.1f} %)")
print(f"  models that answered: {m['models_seen']}")
print(f"  language (heuristic): {m['languages']}")
print(f"  text length: p50 {m['chars']['p50']} | p95 {m['chars']['p95']} chars")
print(f"  latency: p50 {m['latency_ms']['p50']} | p90 {m['latency_ms']['p90']} | "
      f"p95 {m['latency_ms']['p95']} | max {m['latency_ms']['max']} ms")
print(f"  truncated {m['truncated']} | uncalibrated {m['uncalibrated']} | unsupported {m['unsupported']}")

print("\n  by primitive:")
for t, v in m["by_type"].items():
    print(f"    {t:7s} {v['answers']:5d} answers | delegates {v['delegation_rate']*100:5.1f} % | "
          f"mean confidence {v['mean_confidence']:.3f}")

print("\n  why it delegated:")
for k, v in sorted(m["delegate_kinds"].items(), key=lambda x: -x[1]):
    print(f"    {k:38s} {v:5d}")

print("\n  confidence histogram:")
for k, v in m["confidence_hist"].items():
    print(f"    {k:14s} {v:5d}  {'#' * min(60, v)}")

print("\n  neutral-mass histogram (to re-tune the threshold on your own traffic):")
for k, v in m["neutral_mass_hist"].items():
    print(f"    {k:14s} {v:5d}  {'#' * min(60, v)}")

print(f"\n  log: level={m['log']['level']} dir={m['log']['directory']} "
      f"files={m['log']['files']} written={m['log']['written']} errors={m['log']['errors']}")
