#!/usr/bin/env python
"""The demo cases, told as a story.

It does not try to show the model off: it shows the four decisions the harness can make —answer
locally, delegate on low confidence, delegate on neutral mass and delegate on truncation— plus
what it does when the primitive is not supported.

Usage: python scripts/demo.py [--url http://127.0.0.1:8090]
"""
import argparse
import json
from pathlib import Path
import urllib.error
import urllib.request

SENT = "Does this text express positive sentiment?"

CASES = [
    ("local", "clear positive", "I love this product, it changed my life!",
     [{"id": "s", "type": "noul", "instructions": SENT}]),
    ("local", "clear negative", "El producto llegó roto y nadie responde. Una estafa.",
     [{"id": "s", "type": "noul", "instructions": SENT}]),
    # no expectation: the model may get it right or wrong depending on the text, and what
    # matters is that when it is unsure it delegates. Asserting it would make the demo depend on
    # the confidence of one specific case.
    ("", "sarcasm", "Great, another product that broke in a week. Just what I needed.",
     [{"id": "s", "type": "noul", "instructions": SENT}]),
    ("delegate", "neutral (high neutral mass)", "El pedido llegó el martes.",
     [{"id": "s", "type": "noul", "instructions": SENT}]),
    ("delegate", "no content", "", [{"id": "s", "type": "noul", "instructions": SENT}]),
    ("delegate", "long: the ending flips the meaning",
     ("Excelente atención, muy amables, el proceso fue rapidísimo. " * 40)
     + "Sin embargo, al final me cobraron el doble y el producto nunca llegó.",
     [{"id": "s", "type": "noul", "instructions": SENT}]),
    ("delegate", "primitive the model does not support",
     "Me cobraron dos veces la misma factura.",
     [{"id": "c", "type": "choice", "instructions": "Which team should handle this ticket?",
       "options": ["sales", "support", "billing", "other"]}]),
]


def post(url, payload, timeout=180):
    req = urllib.request.Request(url + "/decide", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r), r.status


ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://127.0.0.1:8090")
args = ap.parse_args()

health = json.load(urllib.request.urlopen(args.url + "/health", timeout=60))
print(f"model served: {health['model']} ({health['adapter']}) | "
      f"routing: {health.get('routing') or {'noul': health['model']}}")
print(f"confidence thresholds: {health['delegation']['per_type']} | "
      f"neutral mass: {health['delegation'].get('neutral_mass_threshold', 'off')}")
print()

for expected, label, text, questions in CASES:
    try:
        out, _ = post(args.url, {"state": text, "questions": questions})
    except urllib.error.HTTPError as e:
        print(f"  {label:34s} ERROR HTTP {e.code}: {e.read().decode()[:90]}")
        continue
    a = out["answers"][0]
    decision = "DELEGATE" if a["delegate_to_cloud"] else "local   "
    if expected in ("local", "delegate"):
        mark = "ok" if decision.strip().lower() == expected else "  "
    else:
        mark = "·"
    conf = f"{a['confidence']:.3f}" if a.get("confidence") is not None else "  -  "
    nm = a.get("neutral_mass")
    extra = f"neutral={nm:.2f}" if nm is not None else "neutral=  - "
    cal = "calibrated" if a.get("calibrated") else "raw"
    print(f"  [{mark}] {label:34s} {decision} value={str(a['value']):8s} conf={conf} ({cal}) "
          f"{extra} model={a.get('model_used')}")
    if a["delegate_to_cloud"]:
        print(f"        reason: {a.get('delegate_reason')}")


m = json.load(urllib.request.urlopen(args.url + "/metrics?hours=1", timeout=60))
print()
print("=== what was logged (observability)")
print(f"  requests {m['requests']} | answers {m['answers']} | delegated {m['answers_delegated']} "
      f"({(m['delegation_rate'] or 0) * 100:.1f} %)")
print(f"  reasons: {m['delegate_kinds']}")
print(f"  models: {m['models_seen']}")
print(f"  latency: p50 {m['latency_ms']['p50']} ms | p95 {m['latency_ms']['p95']} ms")
dir_log = m["log"]["directory"]
try:  # show the path relative to the repo: an absolute one leaks the machine layout
    dir_log = str(Path(dir_log).relative_to(Path(__file__).resolve().parent.parent))
except ValueError:
    pass
print(f"  log at: {dir_log} (level {m['log']['level']}, "
      f"{m['log']['written']} written, {m['log']['errors']} errors)")
