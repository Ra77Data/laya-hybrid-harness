#!/usr/bin/env python
"""Concurrency probe: sends N requests in parallel and reports whether the service survived.

Registra el contador de arranques del agente antes y después, así la caída queda atribuida y
no como una sospecha. Imprime el error real de cada petición fallida.

Uso: python scripts/probe_concurrency.py [--url ...] [--counts 1,2,4,8]
"""
import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://127.0.0.1:8090")
ap.add_argument("--counts", default="1,2,4,8")
ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "results/probe_concurrency.json"))
args = ap.parse_args()

PAYLOAD = {
    "state": "Me cobraron dos veces y nadie responde, estoy harto.",
    "questions": [
        {"id": "s", "type": "noul", "instructions": "Does this text express positive sentiment?"},
        {"id": "c", "type": "choice", "instructions": "Which team should handle this ticket?",
         "options": ["sales", "support", "billing", "other"]},
    ],
}


DEPLOYED_PORT = 8090   # el agente de launchd sirve este puerto


def agent_runs() -> tuple[str, str]:
    """(runs, pid) del agente de launchd. Devuelve ('n/a','n/a') si la URL probada no es la suya:
    comparar el contador de OTRO servicio daría un 'SOBREVIVIÓ' que no significa nada."""
    if f":{DEPLOYED_PORT}" not in args.url:
        return "n/a", "n/a"
    try:
        out = subprocess.run(["launchctl", "print", f"gui/{__import__('os').getuid()}/com.cesarmg.laya-decide"],
                             capture_output=True, text=True, timeout=10).stdout
        runs = next((l.split("=")[1].strip() for l in out.splitlines() if "runs =" in l), "?")
        pid = next((l.split("=")[1].strip() for l in out.splitlines() if l.strip().startswith("pid =")), "?")
        return runs, pid
    except Exception:  # noqa: BLE001
        return "?", "?"


def once(i: int) -> dict:
    t0 = time.time()
    try:
        req = urllib.request.Request(args.url + "/decide", data=json.dumps(PAYLOAD).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.load(r)
        by = {a["id"]: a for a in d["answers"]}
        return {"i": i, "ok": True, "ms": (time.time() - t0) * 1000,
                "sent": by["s"]["value"], "route": by["c"]["value"]}
    except urllib.error.HTTPError as e:
        return {"i": i, "ok": False, "ms": (time.time() - t0) * 1000,
                "err": f"HTTP {e.code}: {e.read().decode()[:100]}"}
    except Exception as e:  # noqa: BLE001
        return {"i": i, "ok": False, "ms": (time.time() - t0) * 1000,
                "err": f"{type(e).__name__}: {str(e)[:100]}"}


rows = []
for n in [int(x) for x in args.counts.split(",")]:
    runs0, pid0 = agent_runs()
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=n) as ex:
        rs = list(ex.map(once, range(n)))
    wall = (time.time() - t0) * 1000
    ok = [r for r in rs if r["ok"]]
    lat = sorted(r["ms"] for r in ok)
    time.sleep(3)
    runs1, pid1 = agent_runs()
    medible = runs0 != "n/a"
    sobrevivio = (runs0 == runs1) if medible else None
    print(f"=== {n} concurrent | wall {wall:.0f} ms | completed {len(ok)}/{n}")
    if lat:
        print(f"    per-request latency: min {lat[0]:.0f} | median {lat[len(lat)//2]:.0f} | max {lat[-1]:.0f} ms")
        print(f"    answers: sentiment={sorted({str(r['sent']) for r in ok})} routing={sorted({str(r['route']) for r in ok})}")
    for r in [x for x in rs if not x["ok"]][:3]:
        print(f"    FAILED: {r['err']}")
    if medible:
        print(f"    agent: runs {runs0} -> {runs1} (pid {pid0} -> {pid1}) -> "
              f"{'SURVIVED' if sobrevivio else 'CRASHED AND WAS RESTARTED'}")
    else:
        print(f"    agent: n/a (this instance is not managed by launchd; we only check that "
              f"{len(ok)}/{n} answers came back)")
    rows.append({"n": n, "ok": len(ok), "wall_ms": wall, "lat": lat,
                 "runs_before": runs0, "runs_after": runs1,
                 "survived": sobrevivio,
                 "errores": [r.get("err") for r in rs if not r["ok"]]})
    time.sleep(2)

Path(args.out).parent.mkdir(parents=True, exist_ok=True)
Path(args.out).write_text(json.dumps(rows, indent=2, ensure_ascii=False))
print(f"\nsaved: {args.out}")
