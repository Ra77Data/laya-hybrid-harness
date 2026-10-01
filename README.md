# Hybrid Harness — local decision service with cloud delegation

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)](https://www.python.org/)
[![Model](https://img.shields.io/badge/🤗%20Model-laya--sentiment--multilingual-yellow)](https://huggingface.co/Ramg77/laya-sentiment-multilingual)

A decision service that runs **locally**, reports an **honest confidence**, and **flags when an
answer should be delegated** to a bigger model. It decides *whether* to delegate and says why; making
the cloud call is the client's job, and there is a working example in [`examples/delegate.py`](examples/delegate.py).
The model it serves is configuration, not code.

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

| Finding | Number | 95% interval |
|---|---|---|
| How much more often the model errs on what it delegates | **5.86×** (36.8% vs 6.3%) | the ratio spans **4.1×-8.3×** (36.8% is [30.8; 43.3], 6.3% is [5.2; 7.6]) |
| End-to-end accuracy of the hybrid vs answering everything locally | **+2.76 points** (92.5% vs 89.7%) | **+0.85 to +3.86** under the cloud model's own uncertainty |
| Traffic sent to the cloud to get that | **13%** (228 of 1,740) | — |
| AUC of the neutral-mass gate as a detector of neutral texts | **0.814** | — |

Nothing here is asserted without the script that reproduces it.

**How solid is the headline result?** The hybrid number rests on the 228 delegated answers being
handled by a bigger model. 38 of them were labelled blind to estimate how well that goes: the local
model scores 63.2% and the LLM **84.2% (32/38, 95% CI [69.6; 92.6])**. That interval is wide, so the
honest question is what happens to the conclusion at its edges: propagating it to all 228 delegated
cases puts the hybrid between **90.6% and 93.6%**, against 89.7% answering everything locally. The
gain stays positive across the whole interval (+0.85 to +3.86); the exact size of the gain is
indicative, not the direction. With a single annotator (me) and a noisy truth in the hard cases, that
is the strongest claim the data supports — the detail is in
[`results/SUMMARY_HARNESS_TEST.md`](results/SUMMARY_HARNESS_TEST.md).

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

- **The hash is authoritative.** If the real sha256 of the **weights file** does not match `expect_sha256`,
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

## Documentation

| Document | What it covers |
|---|---|
| [`docs/DEMO.md`](docs/DEMO.md) | the demonstration, with its real output |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | components, contract, routing, guarantees |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | every design decision with its evidence |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | deploy, observe, change, troubleshoot |
| [`docs/LICENSES.md`](docs/LICENSES.md) | third-party licenses, verified |
| [`results/SUMMARY_*.md`](results/) | **the evidence**: every number with its method |

### Where to go deeper

This page is the front door; the operative material lives in the docs, one click away:

| I want to… | Read |
|---|---|
| deploy it as a service, read the logs, change the model or the thresholds | [`docs/OPERATIONS.md`](docs/OPERATIONS.md) |
| understand the contract, the adapters, the routing, the guarantees | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| see why each decision was made, with the data behind it | [`docs/DECISIONS.md`](docs/DECISIONS.md) |
| reproduce a number | [`results/SUMMARY_*.md`](results/) |
| check third-party licenses | [`docs/LICENSES.md`](docs/LICENSES.md) |

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

Un servicio de decisión que corre **local**, responde con una confianza honesta y **marca cuándo una
respuesta debería derivarse** a un modelo más grande. Decide *si* derivar y dice por qué; hacer la
llamada al cloud es trabajo del cliente, y hay un ejemplo que funciona en
[`examples/delegate.py`](examples/delegate.py). El modelo que sirve es configuración, no código.

```bash
make setup    # entorno virtual + dependencias (una vez)
make demo     # arranca el servicio, muestra los casos y las métricas, y lo apaga
```

Funciona en cualquier sistema operativo con el camino por defecto (`transformers`). Los adaptadores
de Laya/CoreML —el motor para el que se construyó— son la variante `make setup-full`, en macOS con
Apple Silicon.

## Qué es esto y qué no

Lo que sigue es el **patrón híbrido y su medición**, no un modelo ganador. En esta tarea el modelo
local pierde contra un baseline que se descarga en dos líneas (86,0 % contra 89,7 %), y hasta un motor
general zero-shot le gana al fine-tune del proyecto.

Lo que sí está medido, y no es común tenerlo medido, es todo lo demás:

| Hallazgo | Número | Intervalo 95 % |
|---|---|---|
| Cuánto más se equivoca el modelo en lo que deriva | **5,86×** (36,8 % contra 6,3 %) | el cociente va de **4,1× a 8,3×** (36,8 % es [30,8; 43,3], 6,3 % es [5,2; 7,6]) |
| Accuracy de punta a punta del híbrido contra responder todo local | **+2,76 puntos** (92,5 % contra 89,7 %) | **+0,85 a +3,86** según la incertidumbre del propio modelo grande |
| Tráfico que va al cloud para lograrlo | **13 %** (228 de 1.740) | — |
| AUC de la compuerta de masa neutral como detector de textos neutros | **0,814** | — |

Nada de esto se afirma sin el script que lo reproduce.

**¿Qué tan sólido es el resultado estrella?** El número híbrido se apoya en que las 228 respuestas
derivadas las conteste un modelo más grande. Se etiquetaron 38 a ciegas para estimar qué tan bien sale
eso: el modelo local acierta 63,2 % y el LLM **84,2 % (32/38, IC95 [69,6; 92,6])**. Ese intervalo es
ancho, así que la pregunta honesta es qué pasa con la conclusión en sus bordes: propagándolo a los 228
derivados, el híbrido queda entre **90,6 % y 93,6 %**, contra 89,7 % respondiendo todo local. La
ganancia se mantiene positiva en todo el intervalo (+0,85 a +3,86); lo indicativo es el tamaño de la
ganancia, no su dirección. Con un solo anotador (yo) y una verdad ruidosa en los casos difíciles, eso
es lo más fuerte que sostienen los datos — el detalle está en
[`results/SUMMARY_HARNESS_TEST.md`](results/SUMMARY_HARNESS_TEST.md).

## Qué muestra el demo

Un comando, sin Apple Silicon y sin infraestructura extra. Cuenta una historia en vez de lucir al
modelo:

| Caso | Qué demuestra |
|---|---|
| positivo / negativo claro | el camino normal: se responde **local** con confianza alta |
| sarcasmo | el modelo **se equivoca** (`value=True`) pero con 0,68 de confianza: el harness **deriva**. No acierta, pero sabe que no sabe |
| neutro ("El pedido llegó el martes.") | `P(neutro)=0,81` supera la compuerta de 0,70: **deriva** en vez de inventar un sentimiento |
| sin contenido | confianza 0,53 → **deriva** |
| texto largo (2.400 caracteres) | 536 tokens contra una ventana de 512 → **deriva**, porque una respuesta segura sobre texto parcial no vale |
| primitiva no soportada | el modelo declara soportar sólo `noul`; una pregunta `choice` vuelve como `unsupported_by_model` y **deriva** en vez de inventar una respuesta |

La transcripción completa, copiada de una corrida real, está en `docs/DEMO.md`.

## Cómo funciona

```
                 ┌──────────────────────────────────────────────┐
   cliente ───►  │  POST /decide                                │
   (agente,      │   1. enrutar por primitiva  (routing)        │
    script,      │   2. llamar al modelo       (adaptador)      │
    app)         │   3. calibrar               (temperatura)    │
                 │   4. decidir                (política)       │
                 │   5. registrar la decisión  (observabilidad) │
                 └───────┬──────────────────────────┬───────────┘
                         │                          │
                 ┌───────▼────────┐        ┌────────▼─────────┐
                 │  adaptadores   │        │  log JSONL       │
                 │  coreml        │        │  + /metrics      │
                 │  laya          │        └──────────────────┘
                 │  transformers  │
                 └───────┬────────┘
                         │
              ┌──────────▼───────────┐
              │  registro de modelos │
              │  (config.yaml)       │
              └──────────────────────┘
```

**El hash manda.** Si el sha256 real del **archivo de pesos** no coincide con `expect_sha256`, ese modelo no se
carga. Salió de un incidente real: el servicio desplegado estaba sirviendo **otro modelo** del que
decía la documentación.

**`calibrated` no miente.** Es verdadero sólo si se aplicó una temperatura de verdad.

**La inferencia está serializada.** MPS/Metal no es thread-safe: sin candado, **dos peticiones
simultáneas abortaban el proceso**.

**El registro nunca puede tumbar una decisión.** Va dentro de un `try/except` y cuenta sus propios
errores.

## Inicio rápido

```bash
make setup    # entorno virtual + dependencias (una vez)
make demo     # arranca el servicio, muestra los casos y las métricas, y lo apaga
```

Funciona en cualquier sistema operativo con el camino por defecto (`transformers`). Los adaptadores de
Laya y CoreML —el motor para el que se construyó esto— son la variante `make setup-full`, en macOS con
Apple Silicon.

Verificado desde un clon limpio, con las cachés de `uv` y de modelos vacías:

| Paso | Tiempo | Qué implica |
|---|---|---|
| `git clone` | 0 s | 61 archivos; ningún venv ni log viaja en el repo |
| `make setup` | 75 s | entorno de 766 MB |
| `make demo` | 148 s | incluye la descarga de 1,1 GB del modelo |
| `make test` | 25 s | self-test + casos límite + concurrencia |

**De cero a un demo funcionando: ~4 minutos.** La prueba quedó en `tests/quickstart_clean.sh` para que
cualquiera la repita.

## Documentación

| Documento | Para qué |
|---|---|
| `docs/DEMO.md` | la demostración, con su salida real |
| `docs/ARCHITECTURE.md` | cómo está armado y por qué |
| `docs/DECISIONS.md` | cada decisión con su evidencia |
| `docs/OPERATIONS.md` | desplegarlo, observarlo, cambiarlo, troubleshooting |
| `docs/LICENSES.md` | terceros, verificado |
| `docs/PLAN.md` | el plan de trabajo por fases |
| `results/SUMMARY_*.md` | **la evidencia**: cada número con su método |

### Dónde profundizar

Esta página es la puerta de entrada; el material operativo vive en los documentos, a un clic:

| Quiero… | Leer |
|---|---|
| desplegarlo como servicio, ver los logs, cambiar el modelo o los umbrales | [`docs/OPERATIONS.md`](docs/OPERATIONS.md) |
| entender el contrato, los adaptadores, el enrutamiento, las garantías | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| ver por qué se tomó cada decisión, con el dato que la sostiene | [`docs/DECISIONS.md`](docs/DECISIONS.md) |
| reproducir un número | [`results/SUMMARY_*.md`](results/) |
| revisar licencias de terceros | [`docs/LICENSES.md`](docs/LICENSES.md) |

## Pendiente

- **Batería con tráfico propio**: la herramienta existe (`scripts/export_eval.py` exporta las
  decisiones registradas para etiquetarlas y medir precisión real), falta acumular tráfico. El
  servicio ya lo registra desde el primer día.

Todo lo demás que estaba acá —observabilidad, el camino `choice`/`score` en los adaptadores de Laya,
los topics del repositorio— está hecho y verificado: ver `docs/VERSIONING.md`.

## Licencia

Apache-2.0 (ver `LICENSE`). El proyecto Laya —su repositorio en GitHub, los paquetes `laya` y
`laya-coreml` y el modelo base— es **Apache-2.0**, y por eso este repositorio usa la misma licencia en
vez de una copyleft: la FSF considera Apache-2.0 incompatible con GPL-2.0.


</details>
