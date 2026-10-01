#!/usr/bin/env python
"""Exporta tráfico real registrado como conjunto para etiquetar.

Cierra el bucle: el servicio registra lo que ve, esto lo convierte en algo etiquetable, y con eso
se puede medir la precisión sobre tráfico propio en vez de sobre el test del dataset.

Uso:
  python scripts/export_eval.py --hours 24 --out results/real_traffic_eval.jsonl [--only-delegated]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from service.config import load_config   # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--hours", type=float, default=24)
ap.add_argument("--config", default=None)
ap.add_argument("--out", default="results/real_traffic_eval.jsonl")
ap.add_argument("--only-delegated", action="store_true",
                help="exportar sólo lo que el servicio mandó al cloud")
ap.add_argument("--max", type=int, default=0, help="0 = sin límite")
args = ap.parse_args()

cfg = load_config(args.config)
directory = Path(cfg.observability.get("directory", "logs/decisions"))

from service.observability import DecisionLog  # noqa: E402

log = DecisionLog(enabled=False, directory=directory)
recs = log._read(args.hours)          # noqa: SLF001 - es la misma clase, no hay API pública de lectura

rows, vistos = [], set()
for r in recs:
    state = r.get("request", {}).get("state")
    if not state:
        continue                       # nivel metadata: no hay texto que etiquetar
    for a in r.get("answers", []):
        if args.only_delegated and not a.get("delegate"):
            continue
        key = (r["request"].get("sha256_8"), a.get("type"), a.get("id"))
        if key in vistos:
            continue
        vistos.add(key)
        rows.append({
            "ts": r["ts"], "id": f"real-{r['request'].get('sha256_8')}-{a.get('id')}",
            "text": state, "lang_guess": r["request"].get("lang_guess"),
            "type": a.get("type"), "model": a.get("model"),
            "pred": a.get("value"), "confidence": a.get("confidence"),
            "neutral_mass": a.get("neutral_mass"), "delegate": a.get("delegate"),
            "delegate_kind": a.get("delegate_kind"),
            "target": None,                # <-- lo que hay que completar para medir precisión
        })
        if args.max and len(rows) >= args.max:
            break
    if args.max and len(rows) >= args.max:
        break

out = Path(args.out)
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    for row in rows:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
print(f"exported {len(rows)} real-traffic decisions ({args.hours} h) -> {out}")
if rows:
    dlg = sum(1 for r in rows if r["delegate"])
    print(f"  delegated: {dlg} ({dlg/len(rows)*100:.1f} %)")
    print(f"  languages: {dict(sorted((k, sum(1 for r in rows if r['lang_guess'] == k)) for k in {r['lang_guess'] for r in rows}))}")
    print("  next step: fill in the 'target' field (1 positive / 0 negative) and measure accuracy")
