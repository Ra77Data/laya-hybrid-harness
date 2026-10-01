#!/usr/bin/env python
"""Mide el motor de decisión general en la misma tarea, formulada como `choice`.

Pregunta que responde: ¿un motor zero-shot al que se le pide elegir entre "positive" y
"negative" rinde como los modelos fine-tuneados para sentimiento (`noul`)? Si rinde igual,
el fine-tune no aportaba nada para esta tarea.

Uso:
  python scripts/battery_choice.py --url http://127.0.0.1:8090 --n 240 \
      --type choice --options positive,negative --out results/battery_choice_laya-base.json
"""
import argparse
import json
import random
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent

def _default_test() -> str:
    """El conjunto de evaluación debe viajar con el harness, no depender de dónde esté el workspace."""
    for c in (HERE / "data/test_extended.jsonl", HERE.parent / "etapa4/test_extended.jsonl"):
        if c.exists():
            return str(c)
    return str(HERE / "data/test_extended.jsonl")


DEFAULT_TEST = _default_test()

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://127.0.0.1:8090")
ap.add_argument("--n", type=int, default=240)
ap.add_argument("--seed", type=int, default=42)
ap.add_argument("--type", default="choice", choices=["choice", "noul", "score"])
ap.add_argument("--options", default="positive,negative")
ap.add_argument("--instructions", default="Does this text express positive sentiment?")
ap.add_argument("--test", default=str(DEFAULT_TEST))
ap.add_argument("--model", default=None, help="fija el modelo, saltando el enrutamiento")
ap.add_argument("--out", default=None)
args = ap.parse_args()

recs = [json.loads(l) for l in Path(args.test).read_text(encoding="utf-8").splitlines() if l.strip()]
rnd = random.Random(args.seed)
by_lang = defaultdict(list)
for r in recs:
    by_lang[r["lang"]].append(r)
sample = []
per = args.n // max(1, len(by_lang))
for lang, rows in sorted(by_lang.items()):
    rnd.shuffle(rows)
    sample.extend(rows[:per])

options = [o for o in args.options.split(",") if o]
# Cómo traducir la respuesta del modelo a la etiqueta binaria del test (1 = positivo).
POSITIVE_VALUES = {"positive", "pos", "positivo", True, 1}
NEGATIVE_VALUES = {"negative", "neg", "negativo", False, 0}


def to_binary(value):
    if value in POSITIVE_VALUES:
        return 1
    if value in NEGATIVE_VALUES:
        return 0
    if isinstance(value, (int, float)) and args.type == "score":
        return None            # un score numérico no es una etiqueta binaria
    return None


def post(path, payload, timeout=120):
    req = urllib.request.Request(args.url + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


health = json.load(urllib.request.urlopen(args.url + "/health", timeout=30))
print(f"routing noul={health['routing'].get('noul')} choice={health['routing'].get('choice')} "
      f"score={health['routing'].get('score')}")
print(f"question type={args.type} options={options} | sample {len(sample)} texts")

rows = []
t0 = time.time()
for r in sample:
    q = {"id": "q", "type": args.type, "instructions": args.instructions}
    if args.type == "choice":
        q["options"] = options
    else:
        q["scale"] = options
    payload = {"state": r["state"], "questions": [q]}
    if args.model:
        payload["model"] = args.model
    out = post("/decide", payload)
    a = out["answers"][0]
    pred = to_binary(a["value"])
    rows.append({"lang": r["lang"], "target": int(r["target"]), "value": a["value"], "pred": pred,
                 "conf": a["confidence"], "model": a["model_used"], "delegate": a["delegate_to_cloud"],
                 "latency_ms": out["latency_ms"]})
wall = time.time() - t0

usable = [x for x in rows if x["pred"] is not None]
unmapped = len(rows) - len(usable)


def acc(sub):
    sub = [x for x in sub if x["pred"] is not None]
    return (sum(1 for x in sub if x["pred"] == x["target"]) / len(sub)) if sub else float("nan")


local = [x for x in usable if not x["delegate"]]
lat = sorted(x["latency_ms"] for x in rows)
res = {
    "model_used": Counter(x["model"] for x in rows).most_common(1)[0][0],
    "question_type": args.type, "options": options, "n": len(rows), "unmapped": unmapped,
    "accuracy": acc(usable),
    "accuracy_by_lang": {l: acc([x for x in usable if x["lang"] == l]) for l in sorted({x["lang"] for x in usable})},
    "delegation_rate": sum(1 for x in usable if x["delegate"]) / max(1, len(usable)),
    "local_only_accuracy": acc(local),
    "local_coverage": len(local) / max(1, len(usable)),
    "mean_confidence": sum(x["conf"] for x in rows) / len(rows),
    "latency_ms_median": lat[len(lat) // 2],
    "wall_seconds": round(wall, 1),
    "rows": rows,
}
print(f"  model that answered  {res['model_used']}")
print(f"  accuracy             {res['accuracy']*100:6.2f}%  ({res['unmapped']} answers not mappable to binary)")
print(f"  by language          " + " ".join(f"{k} {v*100:.1f}" for k, v in res["accuracy_by_lang"].items()))
print(f"  delegation           {res['delegation_rate']*100:6.2f}% | local accuracy {res['local_only_accuracy']*100:.2f}% "
      f"over {res['local_coverage']*100:.0f}%")
print(f"  mean confidence      {res['mean_confidence']:.4f} | median latency {res['latency_ms_median']} ms")
if args.out:
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(res, indent=2))
    print(f"  saved: {args.out}")
