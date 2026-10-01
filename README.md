# Hybrid Harness — local decision service with cloud delegation

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)](https://www.python.org/)
[![Model](https://img.shields.io/badge/🤗%20Model-laya--sentiment--multilingual-yellow)](https://huggingface.co/Ramg77/laya-sentiment-multilingual)

A decision service that runs **locally**, reports an **honest confidence**, and **delegates to the
cloud when it is not sure**. The model it serves is configuration, not code.

```bash
make setup    # virtual environment + dependencies (once)
make demo     # starts the service, shows the cases and the metrics, then shuts it down
```

Works on any operating system with the default path (`transformers`). The Laya/CoreML adapters —the
engine this was built for— are the `make setup-full` variant, on macOS with Apple Silicon.

## What this is, and what it is not

What follows is the **hybrid pattern and its measurement**, not a winning model. On this task the
local model loses to a baseline you can download in two lines (86.0% vs 89.7%), and even a zero-shot
general engine beats the project's fine-tune.

What *is* measured, and is not common to have measured, is everything else:

| Finding | Number |
|---|---|
| How much more often the model errs on what it delegates | **5.86×** (36.8% vs 6.3%) |
| End-to-end accuracy of the hybrid vs answering everything locally | **+2.76 points** (92.5% vs 89.7%) |
| Traffic sent to the cloud to get that | **13%** |
| AUC of the neutral-mass gate as a detector of neutral texts | **0.814** |

Nothing here is asserted without the script that reproduces it.

## What the demo shows

One command, no Apple Silicon, no extra infrastructure. It tells a story rather than showing off:

| Case | What it demonstrates |
|---|---|
| clear positive / negative | the normal path: answered **locally** with high confidence |
| sarcasm | the model **gets it wrong** (`value=True`) but at 0.68 confidence: the harness **delegates**. It does not know the answer, but it knows it does not know |
| neutral ("The order arrived on Tuesday.") | `P(neutral)=0.81` crosses the 0.70 gate: **delegates** instead of inventing a sentiment |
| empty input | confidence 0.53 → **delegates** |
| long text (2,400 chars) | 536 tokens against a 512 window → **delegates**, because a confident answer over partial text is worthless |
| unsupported primitive | the model declares support for `noul` only; a `choice` question comes back as `unsupported_by_model` and **delegates** instead of making something up |

The full transcript, copied from a real run, is in [`docs/DEMO.md`](docs/DEMO.md).

## How it works

```
                 ┌──────────────────────────────────────────────┐
   client  ───►  │  POST /decide                                │
   (agent,       │   1. route by primitive   (routing)          │
    script,      │   2. call the model       (adapter)          │
    app)         │   3. calibrate            (temperature)      │
                 │   4. decide               (policy)           │
                 │   5. log the decision     (observability)    │
                 └───────┬──────────────────────────┬───────────┘
                         │                          │
                 ┌───────▼────────┐        ┌────────▼─────────┐
                 │   adapters     │        │  JSONL log       │
                 │   coreml       │        │  + /metrics      │
                 │   laya         │        └──────────────────┘
                 │   transformers │
                 └───────┬────────┘
                         │
              ┌──────────▼───────────┐
              │  model registry      │
              │  (config.yaml)       │
              └──────────────────────┘
```

**Routing by primitive.** Each primitive (`noul` = yes/no, `choice` = pick one, `score` = ordinal)
can be served by a different model, so a fine-tuned sentiment model and a general zero-shot decision
engine live behind the same endpoint without the client knowing which is which. Every answer says
which model produced it (`model_used`).

**The delegation policy** fires if *any* of these holds, and the reason is written into the response:

1. calibrated confidence below the per-primitive threshold;
2. `P(neutral)` above the neutral-mass threshold (the text has no sentiment to classify);
3. the text did not fit the model's window (it never saw all of it);
4. the model does not implement that primitive.

**Design guarantees**, all visible from `/health`:

- **The hash is authoritative.** If the real sha256 of the weights does not match `expect_sha256`,
  that model is not loaded. This came from a real incident: the deployed service was serving a
  different model than the documentation claimed.
- **`calibrated` does not lie.** It is true only if a temperature was actually applied.
- **Inference is serialized.** MPS/Metal is not thread-safe: without a lock, *two* concurrent
  requests aborted the process.
- **Logging can never take down a decision.** It runs inside `try/except` and counts its own errors.

## Quickstart

```bash
make setup    # environment + demo path (transformers). Any OS.
make demo     # the full demonstration, then it shuts the service down
make test     # model self-test + 19 edge cases + concurrency
```

Verified from a clean clone, with empty `uv` and model caches:

| Step | Time | What it implies |
|---|---|---|
| `git clone` | 0 s | 61 files; no venv or log travels in the repo |
| `make setup` | 75 s | 766 MB environment |
| `make demo` | 148 s | includes the 1.1 GB model download |
| `make test` | 25 s | self-test + edge cases + concurrency |

**From zero to a working demo: ~4 minutes.** The test is in
[`tests/quickstart_clean.sh`](tests/quickstart_clean.sh) so anyone can repeat it.

## Deployment (macOS)

```bash
scripts/install-launchd.sh    # starts at login and restarts if it crashes
scripts/uninstall-launchd.sh
make smoke                     # is it up? which model?
make metrics                   # delegation rate, reasons, latencies, histograms
make report                    # human-readable report of real traffic
```

`KeepAlive` with `SuccessfulExit: false` and `ThrottleInterval: 30`: if the process dies, launchd
brings it back; if the service **refuses to start** (e.g. a hash mismatch), it retries at most once
every 30 seconds instead of hot-looping.

## Documentation

| Document | What it covers |
|---|---|
| [`docs/DEMO.md`](docs/DEMO.md) | the demonstration, with its real output |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | components, contract, routing, guarantees |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | every design decision with its evidence |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | deploy, observe, change, troubleshoot |
| [`docs/LICENSES.md`](docs/LICENSES.md) | third-party licenses, verified |
| [`results/SUMMARY_*.md`](results/) | **the evidence**: every number with its method |

## The service in detail

A FastAPI service that exposes typed decisions (`noul`, `choice`, `score`) over a local model, with a
policy for delegating to the cloud. **The model it serves is configuration, not code**: you change
`active` in `config.yaml` or the `LAYA_ACTIVE_MODEL` variable.

It replaces the V3/V5 service, which had the model hardcoded and an ambiguous calibration.

## Why it exists

Auditing the deployed harness surfaced four problems that this service fixes by design:

| Problem in V3/V5 | What this service does |
|---|---|
| The model was in the code; the V3 service was left running with the PoC model while the documentation said V5 | The adapter and the weights come from `config.yaml`; `/health` reports the **weights hash** and whether it matches the expected one |
| `calibrated: true` meant "a calibration file exists", even when no temperature was applied | `calibrated` is true **only if a T was applied**, and the answer includes `temperature` and, when it could not be applied, `calibration_note` |
| The delegation policy applied only to `choice`; `noul` (sentiment) never delegated | The policy applies to **every** primitive, with a per-type threshold and on calibrated confidence |
| The service did not flag what it could not do | Every model declares `supports`; an unsupported primitive comes back as `unsupported_by_model`, not invented |

## Usage

```bash
.venv/bin/python -m uvicorn service.server:app --host 127.0.0.1 --port 8091
# or with whichever model you want to serve:
LAYA_ACTIVE_MODEL=cardiff-xlmr .venv/bin/python -m uvicorn service.server:app --port 8091
```

### Endpoints

| Endpoint | Returns |
|---|---|
| `GET /health` | active model, adapter, supported primitives, weights hash + `match`, temperatures **per primitive**, per-type thresholds, `smoke_ok` |
| `GET /models` | the full registry and which one is active |
| `POST /decide` | the usual contract (`{state, questions}`), plus the honesty fields |
| `POST /selftest` | runs the cases declared in the config and reports which pass |

The contract of a `noul` answer:

```json
{"id": "sentiment", "type": "noul", "value": true,
 "confidence": 0.9812, "raw_confidence": 0.9723,
 "calibrated": true, "temperature": 0.9, "calibration_note": null,
 "probs": [0.0188, 0.9812], "threshold": 0.75,
 "delegate_to_cloud": false, "delegate_reason": null, "supported": true}
```

## Adapters

| Adapter | Serves | Requirements |
|---|---|---|
| `coreml` | Laya CoreML packages (`model.mlpackage` + `weight.bin`), ANE/GPU | `laya-coreml` |
| `laya` | Laya checkpoints in safetensors, without CoreML (x86/Linux/CI) | `laya` + `torch` |
| `transformers` | Hugging Face classifiers; for 3 classes it reduces to binary with `binary_reduction` | `torch` + `transformers` |

Careful: `laya-coreml` and `laya` **do not share a question schema** (`type`/`instructions` against
`t`/`ins`). The adapter translates; no common shape is assumed.

## Startup guarantees

- If the weights hash is not the one declared in `expect_sha256`, **the service does not start**. It
  is the defence against "I am serving another model and nothing says so".
- It runs the `smoke` self-test at startup. If it fails, it still starts, but `/health` reports
  `smoke_ok: false` and it is written to the log: a model that gets things wrong is a quality problem,
  not an identity one, and it should be debuggable with the service up.

## Evaluation battery

`scripts/battery.py` measures the **pipeline** (model + calibration + threshold), not just the model,
over a deterministic sample of labelled texts:

```bash
bash scripts/run_battery_all.sh          # all three models, changing only LAYA_ACTIVE_MODEL
```

It reports accuracy, delegation rate, **accuracy of the subset answered locally** (what the user gets
without the cloud), mean confidence and latency.

## Routing: sentiment + general engine

Each primitive can be served by a different model (`routing` in `config.yaml`):

```yaml
routing:
  noul: cardiff-xlmr      # sentiment, the best measured
  choice: laya-base       # general zero-shot decision engine
  score: laya-base
preload: [cardiff-xlmr, laya-base]   # the rest of the registry loads on first use
```

A single call can carry all three primitives and every answer says which model produced it
(`model_used`). To compare models without touching the config, `POST /decide` accepts
`"model": "<id>"` and pins that model for all questions.

**Measured finding**: the formulation matters more than the model. The same `laya-base`, on the same
sentiment task and the same 240-text sample, scores **87.5%** when asked as `choice`
(positive/negative) and **53.3%** when asked as `noul` — in the `noul` formulation it answers "no" to
clearly positive texts. A zero-shot engine thus beats this project's fine-tune. Details in
`results/SUMMARY_GENERAL_ENGINE.md`.

**Mind the lazy loading**: loading a model takes 2.7-7 s and the DSH plugin times out at 2.5 s. Every
model that serves a primitive must be in `preload`, or the first question will fail on timeout.

## Daily use

After restarting the machine **the service is already running**: launchd starts it at login. The
terminal you used to start the service from (the "terminal A") is no longer needed.

```bash
# 1. (optional) check that the service is up and with which model
curl -s http://127.0.0.1:8090/health | python3 -m json.tool

# 2. bring up the DSH interface with the Laya tool registered
cd ~/Projects/ml/Hybrid_Harness_V7 && bash scripts/start-dsh.sh
```

If something does not answer:

```bash
launchctl print gui/$(id -u)/com.cesarmg.laya-decide | grep -E 'state|pid|runs'
launchctl kickstart -k gui/$(id -u)/com.cesarmg.laya-decide   # force a restart
tail -50 ~/Projects/ml/Hybrid_Harness_V7/logs/launchd.err.log
```

> **If direnv warns `... .envrc is blocked`, run `direnv allow` in this directory.** The `.envrc` only
> sets `LAYA_SERVICE_URL` and the timeout; the plugin carries the same defaults (8090 and 2500 ms), so
> the warning breaks nothing — but approving it makes the environment explicit. The other variables in
> the `.envrc` are V3 conventions this service does not read.

> **Do not run `Hybrid_Harness_V3/scripts/start-laya-service.sh` any more.** That was the old service
> (PoC model, `choice` calibration). Port 8090 is now held by V7: that script would fail on a busy
> port, and if it did start, it would leave the tool answering with the wrong model.

## Startup and persistence

The service runs as a launchd **LaunchAgent**: it starts at login and restarts on its own if it dies.

```bash
scripts/install-launchd.sh                 # installs and starts it (the `active` model of config.yaml)
LAYA_ACTIVE_MODEL=laya-sentiment-v1 scripts/install-launchd.sh   # or pinning the model
scripts/uninstall-launchd.sh               # unloads it and stops the service
launchctl print gui/$(id -u)/com.cesarmg.laya-decide | grep -E 'state|pid|runs'
tail -f logs/launchd.err.log
```

**Agent, not daemon.** A LaunchAgent starts when **the user logs in**; not before. Starting at boot
without a login would need a LaunchDaemon (as root), which would also have to read the user's model
cache. For a personal machine the agent is the right choice.

Restart policy: `KeepAlive` with `SuccessfulExit: false` and `ThrottleInterval: 30`. If the process
dies (even with `kill -9`) launchd brings it back; if the service **refuses to start** —for example
because the weights hash does not match— it retries at most every 30 seconds instead of hot-looping.

> If `launchctl bootstrap` returns `Bootstrap failed: 5: Input/output error`, it is almost always the
> environment it is run from, not the plist: from a restricted shell it fails and from a normal
> terminal it works. `plutil -lint` on the plist confirms it in a second.

`scripts/service-run.sh` is the entry point launchd uses (foreground, no `tee`); logs go to
`logs/launchd.out.log` and `logs/launchd.err.log`.

## Measured results

- `results/SUMMARY_BATTERY.md` — the three models on the same 240-text battery, with Wilson intervals
  and paired McNemar.
- `results/SUMMARY_PLUGIN_VERIFICATION.md` — both real DSH plugins called against this service, with
  the same 4 cases on v1 and on Cardiff.

## Layout

```
config.yaml              model registry, thresholds and self-test cases
service/config.py        loads and validates the registry
service/backends.py      the three adapters
service/calibration.py   per-primitive temperature, applied and reported honestly
service/schemas.py       HTTP contract (compatible with the DSH plugin)
service/server.py        FastAPI + verified startup + self-test
scripts/                 adapter test, battery and comparison
```

## Concurrency: read before touching the service

**MPS/Metal is not thread-safe.** FastAPI serves synchronous endpoints from a thread pool, so without
serializing, **two concurrent requests abort the process**:

```
failed assertion _status < MTLCommandBufferStatusCommitted in -[IOGPUMetalCommandBuffer ...]
```

The service takes `STATE["infer_lock"]` around every model call (in `/decide` and in the self-test).
Verified up to 16 concurrent requests: 16/16 completed and the agent did not restart. If a new adapter
is ever added, **the model call goes inside the lock**.

## Long texts

`max_length` is configurable per model (Cardiff: 512 tokens). When the text does not fit, the answer
says so (`truncated`, `input_tokens`, `max_length`) and it **delegates anyway**, because a confident
answer over partial text is worthless. The threshold does not save you here: a truncated text can come
back at 0.9 confidence.

## Delegation policy

The threshold lives in `config.yaml` (`delegation.per_type`) and applies to calibrated confidence. The
curve measured over 1,740 texts (Cardiff, current threshold 0.75):

| Threshold | Local coverage | Local error | Hybrid accuracy* |
|---|---|---|---|
| 0.75 | 86.9% | 6.3% | 94.5% |
| 0.85 | 79.4% | 4.3% | 96.6% |
| 0.90 | 71.8% | 3.8% | 97.2% |

\* assuming the cloud gets everything delegated right. Measured for real, with the LLM labelling 38
delegated cases blind: 92.5% against 89.7% answering everything locally, with 13% of traffic
delegated. The details and the limits of that measurement are in `results/SUMMARY_HARNESS_TEST.md`.

## Observability

Every decision is recorded in `logs/decisions/decisions-<date>.jsonl` (one file per day, daily
rotation, the oldest deleted according to `retain_days`).

What each record keeps: time, length and short hash of the text, primitive, **which model answered**,
value, raw and calibrated confidence, temperature applied, neutral mass, whether it was truncated,
whether it delegated and **why** (the reason grouped by kind: `high_neutral_mass`,
`raw_confidence_below_0.75`, `input_truncated`…), latency and calibration version.

Detail level in `config.yaml`:

| `level` | What it keeps of the text |
|---|---|
| `off` | nothing |
| `metadata` | numbers, hash and length only |
| **`excerpt`** (default) | the first `excerpt_chars` characters |
| `full` | the whole text (for debugging) |

**Design guarantee**: logging runs inside a `try/except` and can never take down a decision. Measured
on the first batch: 83 records written, **0 errors**.

```bash
curl -s "http://127.0.0.1:8090/metrics?hours=24" | python3 -m json.tool   # raw metrics
python scripts/report_decisions.py --hours 24                            # readable report
python scripts/export_eval.py --hours 24 --out results/real_eval.jsonl   # export for labelling
```

`/metrics` reports: requests and answers, overall delegation rate and **per primitive**, model mix,
delegation reasons grouped, p50/p90/p95/p99 latencies, confidence and **neutral-mass** histograms,
lengths, languages (a coarse heuristic) and truncations.

The neutral-mass histogram is what makes it possible to re-tune the threshold against the real traffic
mix, which is exactly what cannot be known from the dataset's test split.

## Neutral mass

Cardiff is a 3-class classifier; the binary reduction discards the neutral mass, so a text with no
sentiment ("The order arrived on Tuesday.") comes back positive at 0.768. The policy now also delegates
when `P(neutral)` exceeds `delegation.neutral_mass_threshold` (0.70).

Measured over 600 genuinely neutral texts and the 1,740 non-neutral ones: **AUC 0.81**; at 0.70 it
delegates **32.7%** of the neutrals at a cost of **+3.9 points** of traffic on non-neutrals, which also
carry twice the average error. The full marginal table and why 0.50 was not chosen are in
`results/SUMMARY_HARNESS_TEST.md`.

The `neutral_mass` field travels in every answer, and the delegation reason says so:
`high_neutral_mass(0.809>0.7)`.

## Pending

- **A battery with your own traffic**: the tool exists (`scripts/export_eval.py` exports the logged
  decisions so they can be labelled and real accuracy measured); what is missing is accumulating
  traffic. The service has been logging since day one.

Everything else that used to be here —observability, the `choice`/`score` path on the Laya adapters,
the repository topics— is done and verified: see `docs/VERSIONING.md`.

## License

Apache-2.0 (see [`LICENSE`](LICENSE)). The Laya project —its GitHub repository, the `laya` and
`laya-coreml` packages and the base model— is **Apache-2.0**, which is why this repository uses the
same license rather than a copyleft one: the FSF considers Apache-2.0 incompatible with GPL-2.0.

---

<details>
<summary><h2>🇪🇸 Versión en Español — Haz clic aquí para desplegar</h2></summary>

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)](https://www.python.org/)
[![Model](https://img.shields.io/badge/🤗%20Model-laya--sentiment--multilingual-yellow)](https://huggingface.co/Ramg77/laya-sentiment-multilingual)

# Harness híbrido de decisión local

Un servicio de decisión que corre **local**, responde con una confianza honesta y **deriva al cloud
cuando no está seguro**. El modelo que sirve es configuración, no código.

```bash
make setup    # entorno virtual + dependencias (una vez)
make demo     # arranca el servicio, muestra los casos y las métricas, y lo apaga
```

Funciona en cualquier sistema operativo con el camino por defecto (`transformers`). Los adaptadores
de Laya/CoreML —el motor para el que se construyó— son la variante `make setup-full`, en macOS con
Apple Silicon.

**Qué es y qué no es.** Lo que sigue es el patrón híbrido y su medición, no un modelo ganador: en
esta tarea el modelo local pierde contra un baseline que se descarga con dos líneas (86,0 % contra
89,7 %), y hasta un motor zero-shot lo supera. Lo que sí está medido y no es común tenerlo es el
resto: la curva de derivación, que el modelo se equivoca **5,86× más** en lo que deriva, y que el
patrón completo gana **+2,76 puntos** enviando el 13 % del tráfico al cloud. Nada de eso se afirma
sin el script que lo reproduce.

Mapa de la documentación:

| Documento | Para qué |
|---|---|
| `docs/DEMO.md` | la demostración, con su salida real |
| `docs/ARCHITECTURE.md` | cómo está armado y por qué |
| `docs/DECISIONS.md` | cada decisión con su evidencia |
| `docs/OPERATIONS.md` | desplegarlo, observarlo, cambiarlo, troubleshooting |
| `docs/LICENSES.md` | terceros, verificado |
| `docs/PLAN.md` | el plan de trabajo por fases |
| `results/SUMMARY_*.md` | **la evidencia**: cada número con su método |

## El servicio en detalle

Servicio FastAPI que expone decisiones tipadas (`noul`, `choice`, `score`) sobre un modelo local,
con política de derivación al cloud. **El modelo servido es configuración, no código**: se cambia
`active` en `config.yaml` o la variable `LAYA_ACTIVE_MODEL`.

Reemplaza al servicio de V3/V5, que tenía el modelo cableado y una calibración ambigua.

## Por qué existe

Auditando el harness desplegado aparecieron tres problemas que este servicio corrige por diseño:

| Problema en V3/V5 | Qué hace este servicio |
|---|---|
| El modelo estaba en el código; el servicio de V3 quedó corriendo con el modelo del PoC mientras la documentación decía V5 | El adaptador y los pesos salen de `config.yaml`; `/health` reporta **hash de los pesos** y si coincide con el esperado |
| `calibrated: true` significaba "hay un archivo de calibración", aunque no se aplicara ninguna temperatura | `calibrated` es verdadero **solo si se aplicó una T**, y la respuesta incluye `temperature` y, si no se pudo, `calibration_note` |
| La política de derivación solo aplicaba a `choice`; `noul` (el sentimiento) nunca delegaba | La política aplica a **todas** las primitivas, con umbral por tipo y sobre la confianza calibrada |
| El servicio no marcaba lo que no sabía hacer | Cada modelo declara `supports`; una primitiva no soportada vuelve como `unsupported_by_model`, no inventada |

## Uso

```bash
.venv/bin/python -m uvicorn service.server:app --host 127.0.0.1 --port 8091
# o con el modelo que se quiera servir:
LAYA_ACTIVE_MODEL=cardiff-xlmr .venv/bin/python -m uvicorn service.server:app --port 8091
```

### Endpoints

| Endpoint | Devuelve |
|---|---|
| `GET /health` | modelo activo, adaptador, primitivas soportadas, hash de pesos + `match`, temperaturas **por primitiva**, umbrales por tipo, `smoke_ok` |
| `GET /models` | el registro completo y cuál está activo |
| `POST /decide` | el contrato de siempre (`{state, questions}`), más los campos de honestidad |
| `POST /selftest` | corre los casos declarados en la config y dice cuáles pasan |

Contrato de una respuesta `noul`:

```json
{"id": "sentiment", "type": "noul", "value": true,
 "confidence": 0.9812, "raw_confidence": 0.9723,
 "calibrated": true, "temperature": 0.9, "calibration_note": null,
 "probs": [0.0188, 0.9812], "threshold": 0.75,
 "delegate_to_cloud": false, "delegate_reason": null, "supported": true}
```

## Adaptadores

| Adaptador | Sirve | Requisitos |
|---|---|---|
| `coreml` | Paquetes CoreML de Laya (`model.mlpackage` + `weight.bin`), ANE/GPU | `laya-coreml` |
| `laya` | Checkpoints Laya en safetensors, sin CoreML (x86/Linux/CI) | `laya` + `torch` |
| `transformers` | Clasificadores de Hugging Face; para 3 clases se reduce a binario con `binary_reduction` | `torch` + `transformers` |

Ojo: `laya-coreml` y `laya` **no comparten el esquema de pregunta** (`type`/`instructions` contra
`t`/`ins`). El adaptador traduce; no se asume una forma común.

## Garantías de arranque

- Si el hash de los pesos no es el declarado en `expect_sha256`, **el servicio no arranca**. Es la
  defensa contra "estoy sirviendo otro modelo y nada lo dice".
- Corre el self-test de `smoke` al arrancar. Si falla, arranca igual pero `/health` lo reporta como
  `smoke_ok: false` y queda en el log: un modelo que acierta mal es un problema de calidad, no de
  identidad, y conviene poder depurarlo con el servicio en pie.

## Batería de evaluación

`scripts/battery.py` mide el **pipeline** (modelo + calibración + umbral), no solo el modelo, sobre
una muestra determinista de textos con etiqueta:

```bash
bash scripts/run_battery_all.sh          # los tres modelos, cambiando solo LAYA_ACTIVE_MODEL
```

Reporta accuracy, tasa de derivación, **accuracy del subconjunto que se responde localmente**
(lo que el usuario recibe sin cloud), confianza media y latencia.

## Enrutamiento: sentimiento + motor general

Cada primitiva puede servirse con un modelo distinto (`routing` en `config.yaml`):

```yaml
routing:
  noul: cardiff-xlmr      # sentimiento, el mejor medido
  choice: laya-base       # motor de decisión general, zero-shot
  score: laya-base
preload: [cardiff-xlmr, laya-base]   # el resto del registro se carga al primer uso
```

Una sola llamada puede llevar las tres primitivas y cada respuesta indica con qué modelo se
contestó (`model_used`). Para comparar modelos sin tocar la config, `POST /decide` acepta
`"model": "<id>"` y fija ese modelo para todas las preguntas.

**Hallazgo medido**: la formulación pesa más que el modelo. El mismo `laya-base`, en la misma tarea
de sentimiento y la misma muestra de 240 textos, acierta **87,5 %** si se pregunta como `choice`
(positivo/negativo) y **53,3 %** si se pregunta como `noul` — en la formulación `noul` responde
"no" a textos claramente positivos. Un motor zero-shot supera así al fine-tune del proyecto.
Detalle en `results/SUMMARY_GENERAL_ENGINE.md`.

**Ojo con la carga perezosa**: cargar un modelo tarda 2,7-7 s y el plugin de DSH corta a 2,5 s. Todo
modelo que sirva alguna primitiva debe estar en `preload`, o la primera pregunta fallará por timeout.

## Uso diario

Después de reiniciar la máquina **el servicio ya está corriendo**: launchd lo levanta al iniciar
sesión. La terminal donde antes arrancabas el servicio (la "terminal A") ya no hace falta.

```bash
# 1. (opcional) comprobar que el servicio está arriba y con qué modelo
curl -s http://127.0.0.1:8090/health | python3 -m json.tool

# 2. levantar la interfaz de DSH con la tool de Laya registrada
cd ~/Projects/ml/Hybrid_Harness_V7 && bash scripts/start-dsh.sh
```

Si algo no responde:

```bash
launchctl print gui/$(id -u)/com.cesarmg.laya-decide | grep -E 'state|pid|runs'
launchctl kickstart -k gui/$(id -u)/com.cesarmg.laya-decide   # reiniciarlo a la fuerza
tail -50 ~/Projects/ml/Hybrid_Harness_V7/logs/launchd.err.log
```

> **Si direnv avisa `... .envrc is blocked`, corré `direnv allow` en este directorio.** El
> `.envrc` sólo fija `LAYA_SERVICE_URL` y el timeout; el plugin trae los mismos valores por
> defecto (8090 y 2500 ms), así que el aviso no rompe nada — pero conviene aprobarlo para que el
> entorno quede explícito. Las demás variables del `.envrc` son convenciones de V3 que este
> servicio no lee.

> **No corras más `Hybrid_Harness_V3/scripts/start-laya-service.sh`.** Ese era el servicio viejo
> (modelo del PoC, calibración `choice`). Ahora el puerto 8090 lo ocupa V7: ese script fallaría por
> puerto ocupado, y si llegara a arrancar, dejaría la tool respondiendo con el modelo equivocado.

## Arranque y persistencia

El servicio corre como **LaunchAgent** de launchd: arranca al iniciar sesión y se reinicia solo si
se cae.

```bash
scripts/install-launchd.sh                 # instala y arranca (modelo `active` de config.yaml)
LAYA_ACTIVE_MODEL=laya-sentiment-v1 scripts/install-launchd.sh   # o fijando el modelo
scripts/uninstall-launchd.sh               # lo descarga y detiene el servicio
launchctl print gui/$(id -u)/com.cesarmg.laya-decide | grep -E 'state|pid|runs'
tail -f logs/launchd.err.log
```

**Agente, no daemon.** Un LaunchAgent arranca cuando **el usuario inicia sesión**; no antes. Para
que arranque en el boot sin login haría falta un LaunchDaemon (como root), que además tendría que
poder leer la caché de modelos del usuario. Para una máquina personal el agente es lo correcto.

Política de reinicio: `KeepAlive` con `SuccessfulExit: false` y `ThrottleInterval: 30`. Si el
proceso muere (incluso con `kill -9`) launchd lo levanta; si el servicio **se niega a arrancar**
—por ejemplo porque el hash de los pesos no coincide— reintenta como mucho cada 30 segundos en vez
de entrar en un bucle cerrado.

> Si `launchctl bootstrap` devuelve `Bootstrap failed: 5: Input/output error`, casi siempre es el
> entorno desde el que se ejecuta, no el plist: desde un shell con sandbox restrictivo falla y desde
> una terminal normal funciona. `plutil -lint` sobre el plist lo confirma en un segundo.

`scripts/service-run.sh` es el punto de entrada que usa launchd (primer plano, sin `tee`); los logs
van a `logs/launchd.out.log` y `logs/launchd.err.log`.

## Resultados medidos

- `results/SUMMARY_BATTERY.md` — los tres modelos con la misma batería de 240 textos, con
  intervalos de Wilson y McNemar pareado.
- `results/SUMMARY_PLUGIN_VERIFICATION.md` — los dos plugins reales de DSH llamados contra este
  servicio, con los mismos 4 casos sobre v1 y sobre Cardiff.

## Estructura

```
config.yaml              registro de modelos, umbrales y casos de self-test
service/config.py        carga y valida el registro
service/backends.py      los tres adaptadores
service/calibration.py   temperatura por primitiva, aplicada y reportada con honestidad
service/schemas.py       contrato HTTP (compatible con el plugin de DSH)
service/server.py        FastAPI + arranque verificado + self-test
scripts/                 test de adaptadores, batería y comparación
```

## Concurrencia: leer antes de tocar el servicio

**MPS/Metal no es thread-safe.** FastAPI atiende los endpoints sincrónicos en un pool de hilos, así
que sin serializar, **dos peticiones simultáneas abortan el proceso**:

```
failed assertion _status < MTLCommandBufferStatusCommitted in -[IOGPUMetalCommandBuffer ...]
```

El servicio toma `STATE["infer_lock"]` alrededor de cada llamada al modelo (en `/decide` y en el
self-test). Verificado hasta 16 concurrentes: 16/16 completadas y el agente sin reiniciarse. Si
algunas vez se agrega un adaptador nuevo, **la llamada al modelo va dentro del candado**.

## Textos largos

`max_length` es configurable por modelo (Cardiff: 512 tokens). Cuando el texto no entra, la respuesta
lo dice (`truncated`, `input_tokens`, `max_length`) y **se deriva igual**, porque una respuesta
segura sobre texto parcial no vale. El umbral no salva de esto: un texto truncado puede dar 0,9 de
confianza.

## Política de derivación

El umbral vive en `config.yaml` (`delegation.per_type`) y aplica sobre la confianza calibrada. La
curva medida sobre 1.740 textos (Cardiff, umbral actual 0,75):

| Umbral | Cobertura local | Error local | Accuracy híbrida* |
|---|---|---|---|
| 0,75 | 86,9 % | 6,3 % | 94,5 % |
| 0,85 | 79,4 % | 4,3 % | 96,6 % |
| 0,90 | 71,8 % | 3,8 % | 97,2 % |

\* suponiendo que el cloud acierta todo lo derivado. Medido de verdad, con el LLM etiquetando a
ciegas 38 casos derivados: 92,5 % contra 89,7 % respondiendo todo local, con el 13 % del tráfico
derivado. Los detalles y los límites de esa medición están en
`results/SUMMARY_HARNESS_TEST.md`.

## Observabilidad

Cada decisión queda registrada en `logs/decisions/decisions-<fecha>.jsonl` (un archivo por día,
rotación diaria, los más viejos se borran según `retain_days`).

Qué guarda cada registro: hora, largo y hash corto del texto, primitiva, **qué modelo contestó**,
valor, confianza cruda y calibrada, temperatura aplicada, masa neutral, si se truncó, si se derivó y
**por qué** (el motivo agrupado en su tipo: `high_neutral_mass`, `raw_confidence_below_0.75`,
`input_truncated`…), latencia y versión de calibración.

Nivel de detalle en `config.yaml`:

| `level` | Qué guarda del texto |
|---|---|
| `off` | nada |
| `metadata` | sólo números, hash y largo |
| **`excerpt`** (por defecto) | los primeros `excerpt_chars` caracteres |
| `full` | el texto completo (para depurar) |

**Garantía de diseño**: el registro va dentro de un `try/except` y nunca puede tumbar una decisión.
Medido en la primera tanda: 83 registros escritos, **0 errores**.

```bash
curl -s "http://127.0.0.1:8090/metrics?hours=24" | python3 -m json.tool   # métricas crudas
python scripts/report_decisions.py --hours 24                            # informe legible
python scripts/export_eval.py --hours 24 --out results/real_eval.jsonl   # exportar para etiquetar
```

`/metrics` informa: peticiones y respuestas, tasa de derivación global y **por primitiva**, mezcla de
modelos, motivos de derivación agrupados, latencias p50/p90/p95/p99, histogramas de confianza y de
**masa neutral**, largos, idiomas (heurística gruesa) y truncados.

El histograma de masa neutral es lo que permite recalibrar el umbral con la mezcla real de tráfico,
que es justamente lo que no se puede saber desde el test del dataset.

## Masa neutral

Cardiff es un clasificador de 3 clases; la reducción a binario descarta la masa neutral, así que un
texto sin sentimiento ("El pedido llegó el martes.") sale positivo con 0,768. La política ahora
también deriva cuando `P(neutro)` supera `delegation.neutral_mass_threshold` (0,70).

Medido sobre 600 neutros reales y los 1.740 no neutros: **AUC 0,81**; con 0,70 se deriva el **32,7 %**
de los neutros a cambio de **+3,9 puntos** de tráfico en los no neutros, que además tiene el doble de
error que el promedio. La tabla marginal completa y
por qué no se eligió 0,50 están en `results/SUMMARY_HARNESS_TEST.md`.

El campo `neutral_mass` viaja en cada respuesta, y la razón de derivación lo dice:
`high_neutral_mass(0.809>0.7)`.

## Pendiente

- **Batería con tráfico propio**: la herramienta existe (`scripts/export_eval.py` exporta las
  decisiones registradas para etiquetarlas y medir precisión real), falta acumular tráfico. El
  servicio ya lo registra desde el primer día.

Todo lo demás que estaba acá —observabilidad, el camino `choice`/`score` en los adaptadores de Laya,
los topics del repositorio— está hecho y verificado: ver `docs/VERSIONING.md`.

</details>
