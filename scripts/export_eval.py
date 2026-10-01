#!/usr/bin/env python
"""Exports logged real traffic as a set that can be labelled.

It closes the loop: the service logs what it sees, this turns it into something labelable, and
with that accuracy can be measured on your own traffic instead of on the dataset's test split.

Usage:
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
                help="export only what the service sent to the cloud")
ap.add_argument("--max", type=int, default=0, help="0 = no limit")
args = ap.parse_args()

cfg = load_config(args.config)
directory = Path(cfg.observability.get("directory", "logs/decisions"))

from service.observability import DecisionLog  # noqa: E402

log = DecisionLog(enabled=False, directory=directory)
recs = log._read(args.hours)          # noqa: SLF001 - same class, there is no public read API

rows, seen = [], set()
for r in recs:
    state = r.get("request", {}).get("state")
    if not state:
        continue                       # metadata level: there is no text to label
    for a in r.get("answers", []):
        if args.only_delegated and not a.get("delegate"):
            continue
        key = (r["request"].get("sha256_8"), a.get("type"), a.get("id"))
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "ts": r["ts"], "id": f"real-{r['request'].get('sha256_8')}-{a.get('id')}",
            "text": state, "lang_guess": r["request"].get("lang_guess"),
            "type": a.get("type"), "model": a.get("model"),
            "pred": a.get("value"), "confidence": a.get("confidence"),
            "neutral_mass": a.get("neutral_mass"), "delegate": a.get("delegate"),
            "delegate_kind": a.get("delegate_kind"),
            "target": None,                # <-- what has to be filled in to measure accuracy
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
