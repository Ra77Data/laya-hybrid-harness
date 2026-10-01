# Operations


## Installation

```bash
make setup        # environment + demo path (transformers). Any operating system.
make setup-full   # + Laya adapters and CoreML (macOS with Apple Silicon)
```

The `Makefile` uses `uv` when available and falls back to `python -m venv` otherwise. Extras are
declared in `pyproject.toml`: `[demo]` and `[full]`.

## Running

```bash
make serve                       # foreground, full registry (config.yaml)
LAYA_ACTIVE_MODEL=laya-base make serve
LAYA_PORT=9000 make serve        # another port, without touching the config
```

The variables that matter (see `.env.example`):

| Variable | Purpose |
|---|---|
| `LAYA_CONFIG` | path to another model registry |
| `LAYA_ACTIVE_MODEL` | which model is served by default |
| `LAYA_PORT` | overrides the port in the config |
| `HF_HUB_CACHE` | where downloaded models live |

### As a persistent service (macOS)

```bash
scripts/install-launchd.sh       # starts at login and restarts if it crashes
scripts/uninstall-launchd.sh
launchctl print gui/$(id -u)/com.cesarmg.laya-decide | grep -E 'state|pid|runs'
```

`KeepAlive` with `SuccessfulExit: false` and `ThrottleInterval: 30`: if the process dies, launchd
brings it back; if the service **refuses to start** (for example on a hash mismatch), it retries at
most once every 30 seconds instead of hot-looping.

A LaunchAgent starts **at login**, not before. Starting at boot without a login would require a
LaunchDaemon running as root, which would also need to read the user's model cache.

## Observing it

```bash
make smoke                        # is it up? which model?
make metrics                      # raw metrics for the last 24 h
make report                       # human-readable report
curl -s localhost:8090/health | python3 -m json.tool
```

`/health` reports: active model, adapter, supported primitives, **real sha256 of the weights and
whether it matches the expected one**, **which primitives have a temperature**, the delegation
thresholds, the state of every model in the registry (`loaded`, `smoke_ok`, `error`, `adapter_ready`,
`available`) and the startup self-test.

`/metrics?hours=N` aggregates the logged traffic: delegation overall and per primitive, reasons
grouped by kind, model mix, latency p50/p90/p95/p99, and confidence and neutral-mass histograms.

## Changing things

| I want to change | Where | Applied |
|---|---|---|
| which model serves a primitive | `routing` in `config.yaml` | restart the service |
| the confidence threshold | `delegation.per_type` | restart the service |
| the neutral-mass threshold | `delegation.neutral_mass_threshold` | restart the service |
| which models are preloaded | `preload` | restart the service |
| how much text is kept in the log | `observability.level` | restart the service |
| add a model | an entry under `models:` | restart the service |

With launchd: `launchctl kickstart -k gui/$(id -u)/com.cesarmg.laya-decide`.

**Every policy change is measured before it is fixed in place.** The delegation and neutral-mass
curves are in `results/SUMMARY_HARNESS_TEST.md`, and `scripts/neutral_gate.py` recomputes the second
one on your own traffic.

## Logging and privacy

Every decision goes to `logs/decisions/decisions-<date>.jsonl`, with daily rotation and deletion of
files older than `retain_days` at startup.

| `observability.level` | What it keeps of the text |
|---|---|
| `off` | nothing |
| `metadata` | numbers, hash and length only |
| `excerpt` (default) | the first `excerpt_chars` characters |
| `full` | the whole text |

By default the full text is **not** kept. If the service will process third-party data, `metadata`
is the appropriate level.

To measure accuracy on your own traffic:

```bash
python scripts/export_eval.py --hours 24 --out results/real_eval.jsonl
# fill in the 'target' field (1 positive / 0 negative) and measure
```

## When something fails

| Symptom | Most likely cause | What to do |
|---|---|---|
| `laya_service_unavailable` in the client | the service is down, or still loading models | `make smoke`; wait ~15 s after a restart |
| the service dies under concurrent requests | someone removed the inference lock from `server.py` | see "MPS is not thread-safe" below |
| confident and wrong answers on long texts | `max_length` too small, or the truncation policy disabled | check `max_length` and that `truncated` forces delegation |
| a neutral text comes back positive at 0.77 | the neutral-mass threshold is `null` | set it (0.70 measured; see `results/SUMMARY_HARNESS_TEST.md`) |
| `calibrated: false` on everything | the model in turn has no fitted temperature | that is correct: the confidence is raw and says so |
| the service will not start after changing a model | the hash does not match `expect_sha256` | fix the entry; this is the guarantee working |
| in a new environment: `tiktoken is required to read a tiktoken file` | `protobuf` is missing, which the SentencePiece extractor needs (the message names tiktoken and misleads) | `pip install protobuf`; already in the `[demo]` extra |
| direnv: `.envrc is blocked` | the file has not been approved | `direnv allow` in the directory |
| `launchctl bootstrap: 5: Input/output error` | the shell's permissions, not the plist | try from a normal terminal; `plutil -lint` rules out the plist |

### MPS is not thread-safe (read before touching `server.py`)

FastAPI serves synchronous endpoints from a thread pool. Without serialization, **two concurrent
requests abort the process** with a Metal assertion:

```
failed assertion _status < MTLCommandBufferStatusCommitted in -[IOGPUMetalCommandBuffer ...]
```

The service takes `STATE["infer_lock"]` around every model call, in `/decide` and in the self-test.
Verified up to 16 concurrent requests: 16/16 completed and the agent did not restart. **If a new
adapter is added, the model call goes inside the lock.**

## Verification

```bash
make test                        # self-test + edge cases + concurrency
bash tests/quickstart_clean.sh   # the whole quickstart, in a clean directory
make demo                        # the demonstration, with the expected output in docs/DEMO.md
```

---

<details>
<summary><h2>🇪🇸 Versión en Español — Haz clic aquí para desplegar</h2></summary>

# Operación

## Instalación

```bash
make setup        # entorno + camino del demo (transformers). Cualquier sistema operativo.
make setup-full   # + adaptadores de Laya y CoreML (macOS con Apple Silicon)
```

El `Makefile` usa `uv` si está disponible y si no cae a `python -m venv`. Extras declarados en
`pyproject.toml`: `[demo]` y `[full]`.

## Arranque

```bash
make serve                       # primer plano, registro completo (config.yaml)
LAYA_ACTIVE_MODEL=laya-base make serve
LAYA_PORT=9000 make serve        # otro puerto, sin tocar la config
```

Variables que importan (ver `.env.example`):

| Variable | Para qué |
|---|---|
| `LAYA_CONFIG` | ruta a otro registro de modelos |
| `LAYA_ACTIVE_MODEL` | qué modelo sirve por defecto |
| `LAYA_PORT` | pisa el puerto de la config |
| `HF_HUB_CACHE` | dónde viven los modelos descargados |

### Como servicio persistente (macOS)

```bash
scripts/install-launchd.sh       # arranca al iniciar sesión y se reinicia si se cae
scripts/uninstall-launchd.sh
launchctl print gui/$(id -u)/com.cesarmg.laya-decide | grep -E 'state|pid|runs'
```

`KeepAlive` con `SuccessfulExit: false` y `ThrottleInterval: 30`: si el proceso muere, launchd lo
levanta; si el servicio **se niega a arrancar** (por ejemplo por un hash que no coincide), reintenta
como mucho cada 30 segundos en vez de entrar en un bucle.

Un LaunchAgent arranca **al iniciar sesión**, no antes. Para arrancar en el boot sin login haría
falta un LaunchDaemon como root, que además tendría que poder leer la caché de modelos del usuario.

## Observarlo

```bash
make smoke                        # ¿responde? ¿con qué modelo?
make metrics                      # métricas crudas de las últimas 24 h
make report                       # informe legible
curl -s localhost:8090/health | python3 -m json.tool
```

`/health` reporta: modelo activo, adaptador, primitivas soportadas, **sha256 real de los pesos y si
coincide con el esperado**, **qué primitivas tienen temperatura**, los umbrales de derivación, el
estado de cada modelo del registro (`loaded`, `smoke_ok`, `error`) y el self-test de arranque.

`/metrics?hours=N` agrega el tráfico registrado: derivación global y por primitiva, motivos agrupados
por tipo, mezcla de modelos, latencias p50/p90/p95/p99, histogramas de confianza y de masa neutral.

## Cambiar cosas

| Quiero cambiar | Se toca | Se aplica |
|---|---|---|
| el modelo que sirve una primitiva | `routing` en `config.yaml` | reiniciar el servicio |
| el umbral de confianza | `delegation.per_type` | reiniciar el servicio |
| el umbral de masa neutral | `delegation.neutral_mass_threshold` | reiniciar el servicio |
| qué modelos se precargan | `preload` | reiniciar el servicio |
| cuánto texto se guarda en el registro | `observability.level` | reiniciar el servicio |
| agregar un modelo | una entrada en `models:` | reiniciar el servicio |

Con launchd: `launchctl kickstart -k gui/$(id -u)/com.cesarmg.laya-decide`.

**Todo cambio de política se mide antes de fijarlo.** Las curvas de derivación y de masa neutral
están en `results/SUMMARY_HARNESS_TEST.md`, y `scripts/neutral_gate.py` recalcula la segunda con
tráfico propio.

## Registro y privacidad

Cada decisión va a `logs/decisions/decisions-<fecha>.jsonl`, con rotación diaria y borrado de los
archivos más viejos que `retain_days` al arrancar.

| `observability.level` | Qué guarda del texto |
|---|---|
| `off` | nada |
| `metadata` | sólo números, hash y largo |
| `excerpt` (por defecto) | los primeros `excerpt_chars` caracteres |
| `full` | el texto completo |

Por defecto **no** se guarda el texto completo. Si el servicio va a procesar datos de terceros,
`metadata` es el nivel adecuado.

Para medir precisión sobre tráfico propio:

```bash
python scripts/export_eval.py --hours 24 --out results/real_eval.jsonl
# completar el campo 'target' (1 positivo / 0 negativo) y medir
```

## Cuando algo falla

| Síntoma | Causa más probable | Qué hacer |
|---|---|---|
| `laya_service_unavailable` en el cliente | el servicio no está arriba, o todavía carga modelos | `make smoke`; esperar ~15 s tras un reinicio |
| el servicio muere con varias peticiones a la vez | alguien sacó el candado de inferencia de `server.py` | ver "MPS no es thread-safe" abajo |
| respuestas seguras y equivocadas en textos largos | `max_length` muy chico, o la política de truncación desactivada | revisar `max_length` y que `truncated` fuerce derivación |
| un texto neutro sale positivo con 0,77 | el umbral de masa neutral está en `null` | fijarlo (0,70 medido; ver `SUMMARY_HARNESS_TEST.md`) |
| `calibrated: false` en todo | el modelo de turno no tiene temperatura ajustada | es correcto: la confianza es cruda y se declara |
| el servicio no arranca tras cambiar un modelo | el hash no coincide con `expect_sha256` | corregir la entrada; es la garantía funcionando |
| en un entorno nuevo: `tiktoken is required to read a tiktoken file` | falta `protobuf`, que el extractor de SentencePiece necesita (el mensaje nombra a tiktoken y confunde) | `pip install protobuf`; ya está en el extra `[demo]` |
| direnv: `.envrc is blocked` | falta aprobar el archivo | `direnv allow` en el directorio |
| `launchctl bootstrap: 5: Input/output error` | permisos del shell, no del plist | probar desde una terminal normal; `plutil -lint` para descartar el plist |

### MPS no es thread-safe (leer antes de tocar `server.py`)

FastAPI atiende los endpoints sincrónicos en un pool de hilos. Sin serializar, **dos peticiones
simultáneas abortan el proceso** con una aserción de Metal:

```
failed assertion _status < MTLCommandBufferStatusCommitted in -[IOGPUMetalCommandBuffer ...]
```

El servicio toma `STATE["infer_lock"]` alrededor de cada llamada al modelo, en `/decide` y en el
self-test. Verificado hasta 16 concurrentes: 16/16 completadas y el agente sin reiniciarse. **Si se
agrega un adaptador nuevo, la llamada al modelo va dentro del candado.**

## Verificación

```bash
make test                        # self-test + casos límite + concurrencia
bash tests/quickstart_clean.sh   # el quickstart completo, en un directorio limpio
make demo                        # la demostración, con la salida esperada en docs/DEMO.md
```

</details>
