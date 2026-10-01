#!/usr/bin/env python
"""¿A partir de qué masa neutral conviene derivar?

Mide los DOS lados, que es lo que hace falta para elegir el umbral con datos:

  * textos NEUTROS de verdad (clase 1 del dataset original, que quedó fuera del test de 1.740):
    deberían derivarse;
  * los 1.740 NO neutros ya etiquetados: NO deberían derivarse por este motivo.

Uso: python scripts/neutral_gate.py [--per-lang 200] [--url http://127.0.0.1:8090]
"""
import argparse
import json
import random
import urllib.request
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"
SENT = "Does this text express positive sentiment?"

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://127.0.0.1:8090")
ap.add_argument("--per-lang", type=int, default=200)
ap.add_argument("--seed", type=int, default=7)
ap.add_argument("--out", default=str(HERE / "results/neutral_gate.json"))
args = ap.parse_args()

# --- 1. textos neutros: label == 1 en el mismo dataset y los mismos splits que el test
rnd = random.Random(args.seed)
neutral = []
fuentes = HERE.parent / "etapa4/data"
for lang, f in (("en", "english_test.parquet"), ("de", "german_test.parquet"), ("es", "spanish_test.parquet")):
    p = fuentes / f
    if not p.exists():
        print(f"  warning: {p} missing, skipping {lang}")
        continue
    df = pd.read_parquet(p)
    col = "label" if "label" in df.columns else df.columns[-1]
    neu = df[df[col] == 1]["text"].dropna().drop_duplicates().tolist()
    rnd.shuffle(neu)
    for t in neu[:args.per_lang]:
        neutral.append({"lang": lang, "text": str(t), "target": None})

non = [{"lang": r["lang"], "text": r["state"], "target": int(r["target"])}
       for r in (json.loads(l) for l in (DATA / "test_extended.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())]
print(f"genuinely neutral: {len(neutral)} | labelled non-neutral: {len(non)}")


def ask(text):
    payload = {"state": text, "questions": [{"id": "s", "type": "noul", "instructions": SENT}]}
    req = urllib.request.Request(args.url + "/decide", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        a = json.load(r)["answers"][0]
    return a


def run(items, es_neutro):
    out = []
    for it in items:
        a = ask(it["text"])
        out.append({"lang": it["lang"], "text": it["text"][:120], "neutral_mass": a.get("neutral_mass"),
                    "conf": a["confidence"], "pred": int(bool(a["value"])), "target": it.get("target"),
                    "es_neutro": es_neutro, "delegate": a["delegate_to_cloud"]})
    return out


print("querying neutral texts…")
rows_neu = run(neutral, True)
print("querying non-neutral texts…")
rows_non = run(non, False)
rows = rows_neu + rows_non
Path(args.out).parent.mkdir(parents=True, exist_ok=True)
Path(args.out).write_text(json.dumps(rows, indent=2, ensure_ascii=False))

nm_neu = [r["neutral_mass"] for r in rows_neu if r["neutral_mass"] is not None]
nm_non = [r["neutral_mass"] for r in rows_non if r["neutral_mass"] is not None]
if not nm_neu:
    raise SystemExit("the model is not returning neutral_mass")
print(f"\nneutral mass — neutrals: median {sorted(nm_neu)[len(nm_neu)//2]:.3f} "
      f"(min {min(nm_neu):.3f}, max {max(nm_neu):.3f})")
print(f"neutral mass — non-neutrals: median {sorted(nm_non)[len(nm_non)//2]:.3f} "
      f"(min {min(nm_non):.3f}, max {max(nm_non):.3f})")

print("\n=== neutral-mass threshold: what is gained and what is lost")
print(f"  {'thresh':>7s} {'neutrals delegated':>18s} {'non-neutrals delegated (false pos.)':>36s} {'F1':>6s}")
mejor = None
for t in [x / 100 for x in range(30, 96, 5)]:
    tp = sum(1 for v in nm_neu if v > t) / len(nm_neu)
    fp = sum(1 for v in nm_non if v > t) / len(nm_non)
    f1 = (2 * tp * (1 - fp) / (tp + (1 - fp))) if (tp + (1 - fp)) else 0.0
    print(f"  {t:7.2f} {tp*100:17.1f}% {fp*100:30.1f}% {f1:6.3f}")
    if mejor is None or f1 > mejor[1]:
        mejor = ((t, tp, fp), f1)
print(f"\n  best F1 on this grid: threshold {mejor[0][0]:.2f} -> detects {mejor[0][1]*100:.1f}% of neutrals "
      f"at the cost of {mejor[0][2]*100:.1f}% extra on non-neutrals")

# --- efecto combinado con la compuerta de confianza actual
print("\n=== effect on traffic (the 1,740 non-neutral + the genuinely neutral)")
for t in (0.5, 0.6, 0.7, mejor[0][0]):
    extra = sum(1 for r in rows_non if r["neutral_mass"] and r["neutral_mass"] > t) / len(rows_non)
    base = sum(1 for r in rows_non if r["delegate"]) / len(rows_non)
    print(f"  threshold {t:.2f}: delegation on non-neutrals {base*100:.1f}% -> {(base+extra)*100:.1f}% "
          f"(+{extra*100:.1f} points)")
print(f"\nsaved: {args.out}")
