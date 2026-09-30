#!/usr/bin/env python
"""Bucle de delegación, parte 1: ¿la compuerta apunta a los casos donde el modelo falla?

Recorre el test completo contra el servicio desplegado y cruza dos cosas que ya conocemos sin
necesidad de ninguna etiqueta nueva: la decisión de derivar y el acierto real del modelo local.

Si derivar sirve, la tasa de error del modelo en lo derivado tiene que ser MUCHO mayor que en lo
que responde localmente. Si son parecidas, la compuerta no está discriminando nada.

Uso: python scripts/delegation_loop.py [--n 0]   (0 = todo el test)
"""
import argparse
import json
import random
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SENT = "Does this text express positive sentiment?"

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://127.0.0.1:8090")
ap.add_argument("--n", type=int, default=0, help="0 = todo el conjunto")
ap.add_argument("--seed", type=int, default=42)
ap.add_argument("--blind", type=int, default=60, help="cuántos derivados listar a ciegas para etiquetar")
ap.add_argument("--out", default=str(HERE / "results/delegation_loop.json"))
ap.add_argument("--blind-out", default=str(HERE / "results/delegation_blind.json"))
args = ap.parse_args()

recs = [json.loads(l) for l in (HERE / "data/test_extended.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
rnd = random.Random(args.seed)
if args.n:
    rnd.shuffle(recs)
    recs = recs[:args.n]

print(f"consultando {len(recs)} textos…")
rows = []
t0 = time.time()
for r in recs:
    payload = {"state": r["state"],
               "questions": [{"id": "s", "type": "noul", "instructions": SENT}]}
    req = urllib.request.Request(args.url + "/decide", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        a = json.load(resp)["answers"][0]
    rows.append({"id": r["id"], "lang": r["lang"], "text": r["state"], "target": int(r["target"]),
                 "pred": int(bool(a["value"])), "conf": a["confidence"], "delegate": a["delegate_to_cloud"],
                 "reason": a["delegate_reason"], "truncated": a.get("truncated", False)})
wall = time.time() - t0

loc = [x for x in rows if not x["delegate"]]
dlg = [x for x in rows if x["delegate"]]


def err(sub):
    return sum(1 for x in sub if x["pred"] != x["target"]) / len(sub) if sub else float("nan")


print(f"\n{len(rows)} textos en {wall:.0f}s\n")
print(f"  derivados           {len(dlg):4d}  ({len(dlg)/len(rows)*100:.1f} % del tráfico)")
print(f"  error del modelo en lo DERIVADO     {err(dlg)*100:5.1f} %")
print(f"  error del modelo en lo NO derivado  {err(loc)*100:5.1f} %")
lift = (err(dlg) / err(loc)) if loc and err(loc) > 0 else float("nan")
print(f"  cuántas veces más se equivoca en lo derivado: {lift:.2f}x")
print(f"\n  accuracy si se responde TODO local     {(1-err(rows))*100:.2f} %")
print(f"  accuracy local en lo que sí responde   {(1-err(loc))*100:.2f} %  (cobertura {len(loc)/len(rows)*100:.1f} %)")

print("\n  errores por banda de confianza (todo el conjunto):")
bandas = [(0, 0.60), (0.60, 0.75), (0.75, 0.90), (0.90, 1.01)]
for lo, hi in bandas:
    sub = [x for x in rows if lo <= x["conf"] < hi]
    if sub:
        print(f"    {lo:.2f}-{hi:.2f}: {len(sub):4d} casos | error {err(sub)*100:5.1f} % | "
              f"derivados {sum(1 for x in sub if x['delegate'])/len(sub)*100:5.1f} %")

# listado a ciegas: sin etiqueta, para que el LLM etiquete sin ver la verdad
rnd.shuffle(dlg)
blind = [{"idx": i + 1, "id": x["id"], "lang": x["lang"], "text": x["text"],
          "local_pred": "positivo" if x["pred"] else "negativo", "conf": x["conf"]}
         for i, x in enumerate(dlg[:args.blind])]
Path(args.out).parent.mkdir(parents=True, exist_ok=True)
Path(args.out).write_text(json.dumps(rows, indent=2, ensure_ascii=False))
Path(args.blind_out).write_text(json.dumps(
    {"blind": [{k: v for k, v in b.items() if k != "id"} for b in blind],
     "gold": {str(b["idx"]): next(x["target"] for x in dlg if x["id"] == b["id"]) for b in blind}},
    indent=2, ensure_ascii=False))
print(f"\n  guardado: {args.out}")
print(f"  listado a ciegas: {args.blind_out} ({len(blind)} derivados, sin etiqueta)")
print("\n=== PARA ETIQUETAR A CIEGAS (el modelo local dijo lo que figura en 'local_pred') ===")
for b in blind:
    print(f"{b['idx']:3d} [{b['lang']}] {b['text'][:150]}")
