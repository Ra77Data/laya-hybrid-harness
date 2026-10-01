#!/usr/bin/env python
"""Pipeline evaluation battery (model + calibration + threshold), not just the model.

It takes a deterministic sample of labelled texts, asks the running service over HTTP and
reports what matters for a hybrid deployment:

  * overall accuracy
  * delegation rate to the cloud
  * **accuracy of the subset answered locally** (what the user sees without the cloud)
  * mean confidence and latency

Usage:
  python scripts/battery.py --url http://127.0.0.1:8091 --n 200 --out results/battery_<model>.json
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
    """The evaluation set has to travel with the harness, not depend on where the workspace is."""
    for c in (HERE / "data/test_extended.jsonl", HERE.parent / "etapa4/test_extended.jsonl"):
        if c.exists():
            return str(c)
    return str(HERE / "data/test_extended.jsonl")


DEFAULT_TEST = _default_test()
QUESTION = "Does this text express positive sentiment?"

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://127.0.0.1:8091")
ap.add_argument("--n", type=int, default=200)
ap.add_argument("--seed", type=int, default=42)
ap.add_argument("--test", default=str(DEFAULT_TEST))
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


def post(path, payload, timeout=30):
    req = urllib.request.Request(args.url + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


health = post("/health", {}) if False else json.load(urllib.request.urlopen(args.url + "/health", timeout=30))
model = health["model"]
print(f"model served: {model} ({health['adapter']}) | sample: {len(sample)} texts "
      f"({dict(Counter(r['lang'] for r in sample))})")

rows = []
t0 = time.time()
for r in sample:
    payload = {"state": r["state"],
               "questions": [{"id": "sentiment", "type": "noul", "instructions": QUESTION}]}
    out = post("/decide", payload)
    a = out["answers"][0]
    rows.append({"id": r["id"], "lang": r["lang"], "target": int(r["target"]),
                 "value": bool(a["value"]), "conf": a["confidence"],
                 "raw_conf": a["raw_confidence"], "calibrated": a["calibrated"],
                 "T": a["temperature"], "delegate": a["delegate_to_cloud"],
                 "threshold": a["threshold"], "latency_ms": out["latency_ms"], "supported": a["supported"]})
wall = time.time() - t0


def acc(sub):
    if not sub:
        return float("nan")
    return sum(1 for x in sub if int(x["value"]) == x["target"]) / len(sub)


local = [x for x in rows if not x["delegate"]]
deleg = [x for x in rows if x["delegate"]]
per_lang = {l: acc([x for x in rows if x["lang"] == l]) for l in sorted(set(x["lang"] for x in rows))}
lat = sorted(x["latency_ms"] for x in rows)
res = {
    "model": model, "adapter": health["adapter"], "n": len(rows),
    "weights_match": (health.get("weights") or {}).get("match"),
    "types_with_temperature": health["calibration"].get("types_with_temperature"),
    "threshold_noul": health["delegation"]["per_type"].get("noul"),
    "accuracy": acc(rows),
    "accuracy_by_lang": per_lang,
    "delegation_rate": len(deleg) / len(rows),
    "local_coverage": len(local) / len(rows),
    "local_only_accuracy": acc(local),
    "delegated_accuracy": acc(deleg),
    "mean_confidence": sum(x["conf"] for x in rows) / len(rows),
    "latency_ms_median": lat[len(lat) // 2],
    "latency_ms_p95": lat[int(len(lat) * 0.95)],
    "wall_seconds": round(wall, 1),
    "rows": rows,
}
print(f"  accuracy           {res['accuracy']*100:6.2f}%   (by language: "
      + " ".join(f"{k} {v*100:.1f}" for k, v in per_lang.items()) + ")")
print(f"  delegation         {res['delegation_rate']*100:6.2f}%   local coverage {res['local_coverage']*100:.1f}%")
print(f"  local accuracy     {res['local_only_accuracy']*100:6.2f}%   (on what was delegated: {res['delegated_accuracy']*100:.2f}%)")
print(f"  mean confidence    {res['mean_confidence']:.4f}   median latency {res['latency_ms_median']} ms, p95 {res['latency_ms_p95']} ms")
print(f"  calibration        T for: {res['types_with_temperature']} | noul threshold {res['threshold_noul']}")

if args.out:
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(res, indent=2))
    print(f"  saved: {args.out}")
