#!/usr/bin/env python
"""Comparative summary of the batteries saved in results/battery_*.json."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
files = sorted((HERE / "results").glob("battery_*.json"))
if not files:
    raise SystemExit("no hay baterías en results/")

rows = [json.loads(f.read_text(encoding="utf-8")) for f in files]
w = 22
print(f"{'model':{w}s} {'acc':>7s} {'delegates':>10s} {'local acc':>10s} {'mean conf':>10s} "
      f"{'lat med':>8s} {'T':>5s} {'umbral':>7s}")
for r in sorted(rows, key=lambda x: -x["accuracy"]):
    T = ",".join(str(v) for v in (r.get("types_with_temperature") or [])) or "-"
    print(f"{r['model']:{w}s} {r['accuracy']*100:6.2f}% {r['delegation_rate']*100:6.2f}% "
          f"{r['local_only_accuracy']*100:9.2f}% {r['mean_confidence']:11.4f} "
          f"{r['latency_ms_median']:7.1f}m {T:>5s} {str(r['threshold_noul']):>7s}")

print()
print("By language (accuracy):")
langs = sorted({l for r in rows for l in r["accuracy_by_lang"]})
print(f"{'model':{w}s} " + " ".join(f"{l:>7s}" for l in langs))
for r in sorted(rows, key=lambda x: -x["accuracy"]):
    print(f"{r['model']:{w}s} " + " ".join(f"{r['accuracy_by_lang'].get(l, float('nan'))*100:6.1f}%" for l in langs))
