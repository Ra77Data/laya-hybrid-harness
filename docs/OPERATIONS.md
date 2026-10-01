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
LABEL="${LAYA_LABEL:-com.cesarmg.laya-decide}"   # the default; export LAYA_LABEL to change it
launchctl print gui/$(id -u)/$LABEL | grep -E 'state|pid|runs'
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

With launchd: `launchctl kickstart -k gui/$(id -u)/$LABEL` (see the label above).

**Every policy change is measured before it is fixed in place.** The delegation and neutral-mass
curves are in `results/SUMMARY_HARNESS_TEST.md`, and `scripts/neutral_gate.py` recomputes the second
one on your own traffic.

## Logging and privacy

Every decision goes to `logs/decisions/decisions-<date>.jsonl`, with daily rotation and deletion of
files older than `retain_days` at startup.

| `observability.level` | What it keeps of the text |
|---|---|
| `off` | nothing |
| **`metadata`** (default) | numbers, hash and length only |
| `excerpt` | the first `excerpt_chars` characters |
| `full` | the whole text |

By default **no text is kept**: the level is `metadata`. That is the right default if the service
will process third-party data — and it has a price: with `metadata` there is nothing to label, so
`scripts/export_eval.py` cannot build an evaluation set from real traffic. Measuring accuracy on
your own traffic requires opting into `excerpt` (or `full`) and accepting that text is written to
disk.

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

## Daily use

Point `LAYA_LABEL` at the launchd label if you changed it; the examples below use the default.
`REPO` is simply the directory you cloned this into.

```bash
# 1. (optional) check that the service is up and with which model
curl -s http://127.0.0.1:8090/health | python3 -m json.tool

# 2. bring up the DSH interface with the Laya tool registered
bash scripts/start-dsh.sh
```

If something does not answer:

```bash
LABEL="${LAYA_LABEL:-com.cesarmg.laya-decide}"
launchctl print gui/$(id -u)/$LABEL | grep -E 'state|pid|runs'
launchctl kickstart -k gui/$(id -u)/$LABEL   # force a restart
tail -50 logs/launchd.err.log
```

> **If direnv warns `.envrc is blocked`, run `direnv allow` in this directory.** The `.envrc` only
> sets `LAYA_SERVICE_URL` and the timeout; the plugin carries the same defaults, so the warning
> breaks nothing, but approving it makes the environment explicit.

> **Do not run an older service's start script.** If port 8090 is held by this service, an old
> launcher would fail on a busy port and, if it did start, it would leave the tool answering with
> the wrong model. `make smoke` says which model is being served.

## Verification


```bash
make test                        # self-test + edge cases + concurrency
bash tests/quickstart_clean.sh   # the whole quickstart, in a clean directory
make demo                        # the demonstration, with the expected output in docs/DEMO.md
bash scripts/run_battery_all.sh  # the evaluation battery over every model in the registry
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
LABEL="${LAYA_LABEL:-com.cesarmg.laya-decide}"   # el valor por defecto; export LAYA_LABEL lo cambia
launchctl print gui/$(id -u)/$LABEL | grep -E 'state|pid|runs'
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

Con launchd: `launchctl kickstart -k gui/$(id -u)/$LABEL` (ver el label arriba).

**Todo cambio de política se mide antes de fijarlo.** Las curvas de derivación y de masa neutral
están en `results/SUMMARY_HARNESS_TEST.md`, y `scripts/neutral_gate.py` recalcula la segunda con
tráfico propio.

## Registro y privacidad

Cada decisión va a `logs/decisions/decisions-<fecha>.jsonl`, con rotación diaria y borrado de los
archivos más viejos que `retain_days` al arrancar.

| `observability.level` | Qué guarda del texto |
|---|---|
| `off` | nada |
| **`metadata`** (por defecto) | sólo números, hash y largo |
| `excerpt` | los primeros `excerpt_chars` caracteres |
| `full` | el texto completo |

Por defecto **no se guarda texto**: el nivel es `metadata`. Es el default correcto si el servicio va
a procesar datos de terceros — y tiene un precio: con `metadata` no hay nada que etiquetar, así que
`scripts/export_eval.py` no puede armar un conjunto de evaluación desde el tráfico real. Medir
precisión sobre tráfico propio exige optar por `excerpt` (o `full`) y aceptar que el texto se
escribe a disco.

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

## Uso diario

`LAYA_LABEL` apunta al label de launchd si lo cambiaste; los ejemplos usan el valor por defecto.
`REPO` es simplemente el directorio donde clonaste esto.

```bash
# 1. (opcional) comprobar que el servicio está arriba y con qué modelo
curl -s http://127.0.0.1:8090/health | python3 -m json.tool

# 2. levantar la interfaz de DSH con la tool de Laya registrada
bash scripts/start-dsh.sh
```

Si algo no responde:

```bash
LABEL="${LAYA_LABEL:-com.cesarmg.laya-decide}"
launchctl print gui/$(id -u)/$LABEL | grep -E 'state|pid|runs'
launchctl kickstart -k gui/$(id -u)/$LABEL   # reiniciarlo a la fuerza
tail -50 logs/launchd.err.log
```

> **Si direnv avisa `.envrc is blocked`, corré `direnv allow` en este directorio.** El `.envrc` sólo
> fija `LAYA_SERVICE_URL` y el timeout; el plugin trae los mismos valores por defecto, así que el
> aviso no rompe nada, pero aprobarlo deja el entorno explícito.

> **No corras el script de arranque de una versión vieja.** Si el puerto 8090 lo ocupa este
> servicio, un lanzador viejo fallaría por puerto ocupado y, si llegara a arrancar, dejaría la tool
> respondiendo con el modelo equivocado. `make smoke` dice qué modelo se está sirviendo.

## Verificación


```bash
make test                        # self-test + casos límite + concurrencia
bash tests/quickstart_clean.sh   # el quickstart completo, en un directorio limpio
make demo                        # la demostración, con la salida esperada en docs/DEMO.md
bash scripts/run_battery_all.sh  # la batería de evaluación sobre cada modelo del registro
```

</details>
