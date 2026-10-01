"""Servicio de decisión local, agnóstico del modelo y con enrutamiento por primitiva.

Cada primitiva (`noul`, `choice`, `score`) puede servirse con un modelo distinto según
`routing` en config.yaml. Los modelos se cargan de forma perezosa, salvo los de `preload`.

Garantías, todas verificables desde /health:
  * el sha256 REAL del archivo de pesos se compara con `expect_sha256`;
  * un modelo cuyo hash no coincide **no se carga** y sus respuestas se derivan con motivo;
  * `calibrated` es verdadero solo si se aplicó una temperatura a esa respuesta;
  * una primitiva que el modelo de turno no implementa vuelve como `unsupported_by_model`;
  * cada respuesta dice con qué modelo se contestó (`model_used`).
"""
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from .backends import adapter_status, build_backend
from .calibration import Calibration, apply_temperature, load_calibration
from .config import ModelSpec, load_config
from .observability import DecisionLog
from .schemas import Answer, DecideRequest, DecideResponse, HealthResponse, Question

PRIMITIVES = ("noul", "choice", "score")

CONFIG = load_config()
LOG = DecisionLog(
    enabled=CONFIG.observability.get("enabled", True),
    directory=CONFIG.observability.get("directory", "logs/decisions"),
    level=CONFIG.observability.get("level", "excerpt"),
    excerpt_chars=int(CONFIG.observability.get("excerpt_chars", 160)),
    window=int(CONFIG.observability.get("window", 5000)),
    retain_days=int(CONFIG.observability.get("retain_days", 30)))
STATE: dict = {
    "backends": {},          # id -> Backend ya cargado
    "calibrations": {},      # id -> Calibration
    "smoke": {},             # id -> [resultados]
    "errors": {},            # id -> motivo por el que no se pudo cargar
    "smoke_ok": {},          # id -> bool
    "load_seconds": {},      # id -> segundos de carga
    "lock": threading.Lock(),        # protege la carga de modelos
    # Candado de INFERENCIA, separado y global. MPS/Metal no es thread-safe: dos hilos
    # enviando comandos al mismo MTLCommandBuffer abortan el proceso con
    # "failed assertion _status < MTLCommandBufferStatusCommitted". FastAPI atiende los
    # endpoints sincrónicos en un pool de hilos, así que sin esto DOS peticiones
    # simultáneas tumban el servicio (reproducido: 2 concurrentes -> caída).
    "infer_lock": threading.Lock(),
}


def get_backend(spec: ModelSpec):
    """Carga perezosa con lock. Verifica el hash real antes de dar por bueno el modelo."""
    backend = STATE["backends"].get(spec.id)
    if backend is not None:
        return backend
    with STATE["lock"]:
        backend = STATE["backends"].get(spec.id)
        if backend is not None:
            return backend
        started = time.time()
        candidate = build_backend(spec)
        candidate.load()
        info = candidate.weights_info()
        if info.get("match") is False:
            STATE["errors"][spec.id] = (
                f"weights hash mismatch: {info.get('sha256')} != {info.get('expected')}")
            raise RuntimeError(STATE["errors"][spec.id])
        STATE["backends"][spec.id] = candidate
        STATE["calibrations"][spec.id] = load_calibration(spec.calibration)
        STATE["load_seconds"][spec.id] = round(time.time() - started, 2)
        STATE["errors"].pop(spec.id, None)
        return candidate


def _answer_for(model_id: str, q: Question, item: dict, cal: Calibration) -> Answer:
    probs = [float(p) for p in (item.get("probs") or [])]
    conf, applied, T, note = apply_temperature(probs, q.type, cal, item.get("confidence"))
    thr = CONFIG.threshold_for(q.type)
    delegate = conf < thr
    reason = None
    if delegate:
        reason = (f"calibrated_confidence_below_{thr}({conf:.3f})" if applied
                  else f"raw_confidence_below_{thr}({conf:.3f});no_temperature_for_{q.type}")
    # Masa neutral: un texto sin sentimiento no debería responderse como positivo por descarte.
    nm = item.get("neutral_mass")
    if nm is not None and CONFIG.neutral_mass_threshold is not None and nm > CONFIG.neutral_mass_threshold:
        delegate = True
        reason = (f"high_neutral_mass({nm:.3f}>{CONFIG.neutral_mass_threshold})"
                  + (f";{reason}" if reason else ""))
    truncated = bool(item.get("truncated"))
    if truncated:
        # Si el modelo no vio el texto completo, su respuesta segura no vale: se deriva.
        delegate = True
        reason = (f"input_truncated({item.get('input_tokens')} tokens > "
                  f"{item.get('max_length', '?')})" + (f";{reason}" if reason else ""))
    return Answer(
        id=q.id, type=q.type, value=item.get("value"), model_used=model_id,
        confidence=conf, raw_confidence=round(max(probs), 4) if probs else item.get("confidence"),
        calibrated=applied, temperature=T, calibration_note=note,
        probs=probs, options=item.get("options") or [],
        delegate_to_cloud=delegate, delegate_reason=reason, threshold=thr, supported=True,
        neutral_mass=nm, truncated=truncated, input_tokens=item.get("input_tokens"),
        max_length=item.get("max_length"))


def decide_with(state: str, questions: list[Question], pinned: str | None = None) -> list[Answer]:
    """Lógica única de decisión: la usan /decide y el self-test.

    `pinned` fuerza un modelo para todas las preguntas (comparaciones A/B); sin él se enruta
    cada primitiva según la config.
    """
    groups: dict[str, list[Question]] = {}
    rejected: list[tuple[Question, str, str]] = []
    for q in questions:
        mid = pinned or CONFIG.model_for(q.type)
        spec = CONFIG.spec(mid)
        if q.type not in spec.supports:
            rejected.append((q, f"unsupported_by_model({mid})",
                             f"model '{mid}' declares support only for {sorted(spec.supports)}"))
            continue
        groups.setdefault(mid, []).append(q)

    answers: list[Answer] = []
    for mid, qs in groups.items():
        spec = CONFIG.spec(mid)
        try:
            backend = get_backend(spec)
        except Exception as exc:  # noqa: BLE001
            for q in qs:
                answers.append(Answer(
                    id=q.id, type=q.type, supported=False, model_used=mid,
                    delegate_to_cloud=True, threshold=CONFIG.threshold_for(q.type),
                    delegate_reason=f"model_unavailable({mid})",
                    calibration_note=f"{type(exc).__name__}: {str(exc)[:180]}"))
            continue
        cal = STATE["calibrations"][mid]
        try:
            with STATE["infer_lock"]:
                raw = backend.predict(state, [q.model_dump() for q in qs])
        except Exception as exc:  # noqa: BLE001
            for q in qs:
                answers.append(Answer(
                    id=q.id, type=q.type, supported=False, model_used=mid,
                    delegate_to_cloud=True, threshold=CONFIG.threshold_for(q.type),
                    delegate_reason=f"model_error({mid})",
                    calibration_note=f"{type(exc).__name__}: {str(exc)[:180]}"))
            continue
        for q in qs:
            answers.append(_answer_for(mid, q, raw.get(q.id, {}), cal))

    for q, reason, note in rejected:
        answers.append(Answer(
            id=q.id, type=q.type, supported=False, model_used=pinned or CONFIG.model_for(q.type),
            delegate_to_cloud=True, threshold=CONFIG.threshold_for(q.type),
            delegate_reason=reason, calibration_note=note))
    order = {q.id: i for i, q in enumerate(questions)}
    return sorted(answers, key=lambda a: order.get(a.id, 0))


def run_smoke_tests(verbose: bool = True, only: list[str] | None = None) -> dict[str, list[dict]]:
    """Corre los casos de self-test de cada modelo **contra ese modelo**, sin enrutar.

    Enrutar el self-test lo haría pasar por otro modelo y no verificaría nada del declarado.
    """
    out: dict[str, list[dict]] = {}
    for mid, spec in CONFIG.models.items():
        if only is not None and mid not in only:
            continue
        if not spec.smoke:
            continue
        listo, motivo_adapter = adapter_status(spec.adapter)
        if not listo:
            out[mid] = [{"skipped": True, "reason": motivo_adapter}]
            STATE["smoke_ok"][mid] = None
            if verbose:
                print(f"  [selftest:{mid}] SKIPPED ({motivo_adapter})", flush=True)
            continue
        if not spec.available:
            # Un modelo cuyos pesos no están en esta máquina no es un fallo: es una entrada del
            # registro que acá no aplica. Darlo por fallado hacía que una instalación limpia
            # reportara self-test roto por modelos que nunca se propuso servir.
            out[mid] = [{"skipped": True, "reason": spec.unavailable_reason}]
            STATE["smoke_ok"][mid] = None
            if verbose:
                print(f"  [selftest:{mid}] SKIPPED ({spec.unavailable_reason})", flush=True)
            continue
        try:
            backend = get_backend(spec)
        except Exception as exc:  # noqa: BLE001
            out[mid] = [{"ok": False, "error": f"no se pudo cargar: {type(exc).__name__}: {exc}"}]
            STATE["smoke_ok"][mid] = False
            continue
        cal = STATE["calibrations"][mid]
        recs = []
        for case in spec.smoke:
            q = Question(id="smoke", type=case["type"], instructions=case.get("instructions", ""),
                         options=case.get("options") or [], scale=case.get("scale") or [])
            try:
                with STATE["infer_lock"]:
                    item = backend.predict(case["text"], [q.model_dump()])[q.id]
                ans = _answer_for(mid, q, item, cal)
                ok = bool(ans.supported and ans.value == case["expect_value"])
                recs.append({"text": case["text"][:70], "type": case["type"],
                             "expected": case["expect_value"], "got": ans.value,
                             "confidence": ans.confidence, "calibrated": ans.calibrated, "ok": ok})
            except Exception as exc:  # noqa: BLE001
                recs.append({"text": case["text"][:70], "type": case["type"],
                             "expected": case["expect_value"], "got": None, "ok": False,
                             "error": f"{type(exc).__name__}: {exc}"})
        out[mid] = recs
        STATE["smoke_ok"][mid] = all(r["ok"] for r in recs)
        if verbose:
            for r in recs:
                mark = "OK " if r["ok"] else "FAIL"
                print(f"  [selftest:{mid}] {mark} expected={r['expected']} "
                      f"got={r.get('got')} | {r['text'][:50]}", flush=True)
    return out


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[startup] active model: {CONFIG.active} | routing: {CONFIG.routing}", flush=True)
    for mid in CONFIG.preload:
        spec = CONFIG.spec(mid)
        try:
            backend = get_backend(spec)
        except Exception as exc:  # noqa: BLE001
            print(f"[startup] ERROR loading '{mid}': {STATE['errors'].get(mid) or exc}", flush=True)
            if mid == CONFIG.active:
                raise
            continue
        w = backend.weights_info()
        print(f"[startup] {mid}: {w.get('path')}", flush=True)
        print(f"[startup]   sha256={str(w.get('sha256'))[:16]}… expected={str(w.get('expected'))[:16]}… "
              f"matches={w.get('match')} ({STATE['load_seconds'].get(mid)}s)", flush=True)
        print(f"[startup]   calibration: "
              f"{STATE['calibrations'][mid].as_dict()['types_with_temperature'] or 'none'}", flush=True)
    STATE["smoke"] = run_smoke_tests(verbose=True, only=CONFIG.preload)
    print(f"[startup] self-test: {STATE['smoke_ok']} | "
          f"lazy load pending: {[m for m in CONFIG.models if m not in STATE['backends']]}", flush=True)
    borrados = LOG.prune()
    print(f"[startup] observability: level={LOG.level} dir={LOG.directory} "
          f"(old files deleted: {borrados})", flush=True)
    yield


app = FastAPI(title="Laya Decision Service", version="2.0.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
def health():
    models = {}
    for mid, spec in CONFIG.models.items():
        loaded = mid in STATE["backends"]
        info = STATE["backends"][mid].weights_info() if loaded else {}
        models[mid] = {
            "label": spec.label, "adapter": spec.adapter, "supports": sorted(spec.supports),
            "loaded": loaded, "role": [qt for qt in PRIMITIVES if CONFIG.model_for(qt) == mid],
            "adapter_ready": adapter_status(spec.adapter)[0], "available": spec.available,
            "weights": info, "load_seconds": STATE["load_seconds"].get(mid),
            "calibration": (STATE["calibrations"][mid].as_dict() if loaded
                            else {"configured": bool(spec.calibration)}),
            "smoke_ok": STATE["smoke_ok"].get(mid),
            "error": STATE["errors"].get(mid),
        }
    # Sólo cuentan los modelos que sirven alguna primitiva: los demás son alternativas del registro.
    any_error = any(m["error"] for m in models.values() if m["role"])
    return HealthResponse(
        status="ok" if STATE["backends"] and not any_error else "degraded",
        model=CONFIG.active, label=CONFIG.spec().label, adapter=CONFIG.spec().adapter,
        supports=sorted(CONFIG.spec().supports),
        weights=STATE["backends"].get(CONFIG.active, None).weights_info() if CONFIG.active in STATE["backends"] else {},
        calibration=(STATE["calibrations"][CONFIG.active].as_dict()
                     if CONFIG.active in STATE["calibrations"] else {"configured": False}),
        delegation={"default": CONFIG.default_threshold,
                    "per_type": {t: CONFIG.threshold_for(t) for t in PRIMITIVES},
                    "neutral_mass_threshold": CONFIG.neutral_mass_threshold},
        smoke_ok=(all(STATE["smoke_ok"].get(m) for m in CONFIG.preload
                      if STATE["smoke_ok"].get(m) is not None) if STATE["smoke_ok"] else None),
        routing=CONFIG.routing, models=models)


@app.get("/metrics")
def metrics(hours: float = 24):
    """Lo que pasó de verdad en el servicio: derivación, motivos, modelos, latencias, mezclas."""
    return LOG.metrics(hours=hours)


@app.get("/models")
def models():
    return {"active": CONFIG.active, "routing": CONFIG.routing, "preload": CONFIG.preload,
            "available": [{"id": m.id, "label": m.label, "adapter": m.adapter,
                           "supports": sorted(m.supports),
                           "role": [qt for qt in PRIMITIVES if CONFIG.model_for(qt) == m.id],
                           "weights": m.weights, "loaded": m.id in STATE["backends"],
                           "has_calibration": bool(m.calibration)} for m in CONFIG.models.values()]}


@app.post("/selftest")
def selftest():
    if not STATE["backends"]:
        raise HTTPException(status_code=503, detail=STATE["errors"] or "sin modelos cargados")
    results = run_smoke_tests(verbose=False)
    evaluados = [r for recs in results.values() for r in recs if "ok" in r]
    omitidos = [mid for mid, recs in results.items() if recs and recs[0].get("skipped")]
    return {"active": CONFIG.active, "results": results,
            "passed": all(r["ok"] for r in evaluados),
            "tested": len(evaluados), "skipped_models": omitidos}


@app.post("/decide", response_model=DecideResponse)
def decide(request: DecideRequest):
    started = time.perf_counter()
    if not STATE["backends"] and STATE["errors"]:
        raise HTTPException(status_code=503, detail=str(STATE["errors"]))
    try:
        answers = decide_with(request.state, request.questions, pinned=request.model)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"backend_error: {exc}") from exc
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    payload = [a.model_dump() for a in answers]
    LOG.record(state=request.state, questions=[q.model_dump() for q in request.questions],
               answers=payload, latency_ms=latency_ms, model=CONFIG.active,
               calibration_version=STATE["calibrations"].get(CONFIG.active, Calibration()).version,
               routing=CONFIG.routing)
    return DecideResponse(model=CONFIG.active, adapter=CONFIG.spec().adapter,
                          calibration_version=STATE["calibrations"].get(
                              CONFIG.active, Calibration()).version,
                          latency_ms=latency_ms, answers=payload)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=CONFIG.host, port=CONFIG.port)
