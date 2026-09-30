#!/usr/bin/env python
"""Los casos del demo, contados como una historia.

No busca lucir al modelo: muestra las cuatro decisiones que el harness puede tomar —responder
local, derivar por baja confianza, derivar por masa neutral y derivar por truncación— más lo que
hace cuando la primitiva no está soportada.

Uso: python scripts/demo.py [--url http://127.0.0.1:8090]
"""
import argparse
import json
import urllib.error
import urllib.request

SENT = "Does this text express positive sentiment?"

CASOS = [
    ("local", "positivo claro", "I love this product, it changed my life!",
     [{"id": "s", "type": "noul", "instructions": SENT}]),
    ("local", "negativo claro", "El producto llegó roto y nadie responde. Una estafa.",
     [{"id": "s", "type": "noul", "instructions": SENT}]),
    # sin expectativa: el modelo acierta o falla según el texto, y lo que importa es que si duda,
    # derive. Afirmarlo haría que el demo dependiera de la confianza de un caso puntual.
    ("", "sarcasmo", "Great, another product that broke in a week. Just what I needed.",
     [{"id": "s", "type": "noul", "instructions": SENT}]),
    ("deriva", "neutro (masa neutral alta)", "El pedido llegó el martes.",
     [{"id": "s", "type": "noul", "instructions": SENT}]),
    ("deriva", "sin contenido", "", [{"id": "s", "type": "noul", "instructions": SENT}]),
    ("deriva", "largo: el final cambia el sentido",
     ("Excelente atención, muy amables, el proceso fue rapidísimo. " * 40)
     + "Sin embargo, al final me cobraron el doble y el producto nunca llegó.",
     [{"id": "s", "type": "noul", "instructions": SENT}]),
    ("deriva", "primitiva que el modelo no soporta",
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
print(f"modelo servido: {health['model']} ({health['adapter']}) | "
      f"routing: {health.get('routing') or {'noul': health['model']}}")
print(f"umbral de confianza: {health['delegation']['per_type']} | "
      f"masa neutral: {health['delegation'].get('neutral_mass_threshold', 'apagada')}")
print()

for esperado, etiqueta, texto, preguntas in CASOS:
    try:
        out, _ = post(args.url, {"state": texto, "questions": preguntas})
    except urllib.error.HTTPError as e:
        print(f"  {etiqueta:34s} ERROR HTTP {e.code}: {e.read().decode()[:90]}")
        continue
    a = out["answers"][0]
    decision = "DERIVA" if a["delegate_to_cloud"] else "local "
    if esperado in ("local", "deriva"):
        marca = "ok" if decision.strip().lower() == esperado else "  "
    else:
        marca = "·"
    conf = f"{a['confidence']:.3f}" if a.get("confidence") is not None else "  -  "
    nm = a.get("neutral_mass")
    extra = f"neutral={nm:.2f}" if nm is not None else "neutral=  - "
    cal = "calibrada" if a.get("calibrated") else "cruda"
    print(f"  [{marca}] {etiqueta:34s} {decision} value={str(a['value']):8s} conf={conf} ({cal}) "
          f"{extra} modelo={a.get('model_used')}")
    if a["delegate_to_cloud"]:
        print(f"        motivo: {a.get('delegate_reason')}")


m = json.load(urllib.request.urlopen(args.url + "/metrics?hours=1", timeout=60))
print()
print("=== lo que quedó registrado (observabilidad)")
print(f"  peticiones {m['requests']} | respuestas {m['answers']} | derivadas {m['answers_delegated']} "
      f"({(m['delegation_rate'] or 0) * 100:.1f} %)")
print(f"  motivos: {m['delegate_kinds']}")
print(f"  modelos: {m['models_seen']}")
print(f"  latencia: p50 {m['latency_ms']['p50']} ms | p95 {m['latency_ms']['p95']} ms")
print(f"  registro en: {m['log']['directory']} (nivel {m['log']['level']}, "
      f"{m['log']['written']} escritos, {m['log']['errors']} errores)")
