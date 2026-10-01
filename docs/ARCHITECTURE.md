# Architecture


## What it is

A **local decision service** that answers typed questions about a text and decides, per answer,
whether to keep it local or delegate to a large model. What sets it apart is not the model: it is
that **the model is configuration**, that the confidence it reports is verifiable, and that every
decision is logged.

```
                 ┌──────────────────────────────────────────────┐
   client  ───►  │  POST /decide                                │
   (agent,       │                                              │
    script,      │   1. route by primitive   (routing)          │
    app)         │   2. call the model       (adapter)          │
                 │   3. calibrate            (temperature)      │
                 │   4. decide               (policy)           │
                 │   5. log the decision     (observability)    │
                 └───────┬──────────────────────────┬───────────┘
                         │                          │
                 ┌───────▼────────┐        ┌────────▼─────────┐
                 │  adapters      │        │  JSONL log       │
                 │  coreml        │        │  + /metrics      │
                 │  laya          │        └──────────────────┘
                 │  transformers  │
                 └───────┬────────┘
                         │
              ┌──────────▼───────────┐
              │  model registry      │
              │  (config.yaml)       │
              └──────────────────────┘
```

## Why it exists

Auditing the deployed harness surfaced four problems that this service fixes by design:

| Problem in V3/V5 | What this service does |
|---|---|
| The model was in the code; the V3 service was left running with the PoC model while the documentation said V5 | The adapter and the weights come from `config.yaml`; `/health` reports the **weights hash** and whether it matches the expected one |
| `calibrated: true` meant "a calibration file exists", even when no temperature was applied | `calibrated` is true **only if a T was applied**, and the answer includes `temperature` and, when it could not be applied, `calibration_note` |
| The delegation policy applied only to `choice`; `noul` (sentiment) never delegated | The policy applies to **every** primitive, with a per-type threshold and on calibrated confidence |
| The service did not flag what it could not do | Every model declares `supports`; an unsupported primitive comes back as `unsupported_by_model`, not invented |

## Components

| Module | Responsibility | What it guarantees |
|---|---|---|
| `service/config.py` | loads and validates `config.yaml` | an invalid entry is caught at startup; a **missing model does not** prevent startup |
| `service/backends.py` | the three adapters | one interface over different runtimes, and one canonical answer shape |
| `service/calibration.py` | per-primitive temperature | `calibrated` is true **only if a temperature was applied** |
| `service/server.py` | FastAPI, routing, policy | every answer says which model produced it and why it was delegated |
| `service/observability.py` | logging and metrics | logging can **never** take down a decision |
| `service/schemas.py` | HTTP contract | backwards compatible: fields are only ever added |

## The contract

```jsonc
POST /decide
{ "state": "the text to decide over",
  "questions": [ { "id": "s", "type": "noul", "instructions": "Is it positive?" } ],
  "model": null }          // optional: pin the model, skipping routing (for comparisons)
```

```jsonc
{ "model": "cardiff-xlmr", "latency_ms": 57.6,
  "answers": [{
    "id": "s", "type": "noul", "value": true, "model_used": "cardiff-xlmr",
    "confidence": 0.768, "raw_confidence": 0.768,
    "calibrated": false, "temperature": null,
    "calibration_note": "no temperature for 'noul' (no calibration file)",
    "neutral_mass": 0.81, "probs": [0.232, 0.768], "threshold": 0.75,
    "delegate_to_cloud": true, "delegate_reason": "high_neutral_mass(0.809>0.7)",
    "supported": true, "truncated": false, "input_tokens": 21, "max_length": 512 }] }
```

Three primitives, taken from the decision engine this harness integrates:

| Primitive | Question | Answer |
|---|---|---|
| `noul` | does this statement hold? | boolean + P(true) |
| `choice` | which of these options? | option + distribution |
| `score` | how much, on this scale? | level + distribution (+ raw numeric value) |


## Adapters

| Adapter | Serves | Requirements |
|---|---|---|
| `coreml` | Laya CoreML packages (`model.mlpackage` + `weight.bin`), ANE/GPU | `laya-coreml` |
| `laya` | Laya checkpoints in safetensors, without CoreML (x86/Linux/CI) | `laya` + `torch` |
| `transformers` | Hugging Face classifiers; for 3 classes it reduces to binary with `binary_reduction` (the neutral mass is discarded here, which is what the neutral-mass gate compensates for) | `torch` + `transformers` |

Careful: `laya-coreml` and `laya` **do not share a question schema** (`type`/`instructions` against
`t`/`ins`). The adapter translates; no common shape is assumed.

## Routing by primitive

Each primitive can be served by **a different model**: that is what allows a fine-tuned sentiment
model and a general zero-shot decision engine to coexist in one service, without the client knowing
which is which.

```yaml
routing:
  noul: cardiff-xlmr      # sentiment
  choice: laya-base       # general zero-shot engine
  score: laya-base
preload: [cardiff-xlmr, laya-base]
```

If the model in turn does not declare support for a primitive, the answer comes back as
`unsupported_by_model` and is delegated: **no answer is ever invented**. `preload` matters because
loading a model takes seconds and the client's timeout can be shorter.

## The delegation policy

It delegates if **any** of these holds, and the reason is written into the response:

| Condition | Why | Measured in |
|---|---|---|
| calibrated confidence < per-primitive threshold | the model is unsure | `results/SUMMARY_HARNESS_TEST.md` |
| `P(neutral)` > `neutral_mass_threshold` | the text has no sentiment to classify | same |
| the text did not fit the model's window | it never saw all of it: its confidence is worthless | same |
| the model does not support that primitive | it cannot answer it | — |

**The service flags the delegation; it does not perform it.** It has no cloud credentials and no
vendor SDK, and it answers with `delegate_to_cloud` plus a machine-readable reason instead of
silently falling back. Making the cloud call is the client's job: `examples/delegate.py` does it
against any OpenAI-compatible endpoint, and `make delegate TEXT="..."` runs it.

## Design guarantees

1. **The hash is authoritative.** If the real sha256 of the weights does not match `expect_sha256`,
   that model is not loaded and the service says so. This came from a real incident: the deployed
   service was serving **a different model** than the documentation claimed.
2. **`calibrated` does not lie.** It is true only if a temperature was applied to that answer. It
   used to mean "a calibration file exists", which is a different thing.
3. **Inference is serialized.** MPS/Metal is not thread-safe: without a lock, **two concurrent
   requests aborted the process**. See `docs/OPERATIONS.md`.
4. **Logging can never take down a decision.** It runs inside `try/except` and counts its own errors.
5. **What is not known is declared.** Unsupported primitive, truncated text, uncalibrated
   confidence: all of it travels in the response instead of staying implicit.

## See also

- `docs/DECISIONS.md` — every decision with the evidence behind it.
- `docs/OPERATIONS.md` — how it is deployed, observed and changed.
- `results/SUMMARY_*.md` — the measurements, with their method.

---

<details>
<summary><h2>🇪🇸 Versión en Español — Haz clic aquí para desplegar</h2></summary>

# Arquitectura

## Qué es

Un **servicio local de decisión** que responde preguntas tipadas sobre un texto y decide, en cada
respuesta, si se queda local o se deriva a un modelo grande. Lo que lo distingue no es el modelo:
es que **el modelo es configuración**, que la confianza que reporta es verificable y que cada
decisión queda registrada.

```
                 ┌──────────────────────────────────────────────┐
   cliente  ───► │  POST /decide                                │
   (agente,      │                                              │
    script,      │   1. enruta por primitiva  (routing)         │
    app)         │   2. llama al modelo        (adaptador)      │
                 │   3. calibra               (temperatura)     │
                 │   4. decide                 (política)       │
                 │   5. registra               (observabilidad) │
                 └───────┬──────────────────────────┬───────────┘
                         │                          │
                 ┌───────▼────────┐        ┌────────▼─────────┐
                 │  adaptadores   │        │  registro JSONL  │
                 │  coreml        │        │  + /metrics      │
                 │  laya          │        └──────────────────┘
                 │  transformers  │
                 └───────┬────────┘
                         │
              ┌──────────▼───────────┐
              │  modelos del registro │
              │  (config.yaml)        │
              └───────────────────────┘
```

## Por qué existe

Auditando el harness desplegado aparecieron cuatro problemas que este servicio corrige por diseño:

| Problema en V3/V5 | Qué hace este servicio |
|---|---|
| El modelo estaba en el código; el servicio de V3 quedó corriendo con el modelo del PoC mientras la documentación decía V5 | El adaptador y los pesos salen de `config.yaml`; `/health` reporta **hash de los pesos** y si coincide con el esperado |
| `calibrated: true` significaba "hay un archivo de calibración", aunque no se aplicara ninguna temperatura | `calibrated` es verdadero **solo si se aplicó una T**, y la respuesta incluye `temperature` y, si no se pudo, `calibration_note` |
| La política de derivación solo aplicaba a `choice`; `noul` (el sentimiento) nunca delegaba | La política aplica a **todas** las primitivas, con umbral por tipo y sobre la confianza calibrada |
| El servicio no marcaba lo que no sabía hacer | Cada modelo declara `supports`; una primitiva no soportada vuelve como `unsupported_by_model`, no inventada |

## Componentes

| Módulo | Responsabilidad | Qué garantiza |
|---|---|---|
| `service/config.py` | carga y valida `config.yaml` | una entrada inválida se detecta al arrancar; un modelo ausente **no** impide arrancar |
| `service/backends.py` | los tres adaptadores | una interfaz común para runtime distintos, y una forma canónica de respuesta |
| `service/calibration.py` | temperatura por primitiva | `calibrated` es verdadero **sólo si se aplicó** una temperatura |
| `service/server.py` | FastAPI, enrutamiento, política | cada respuesta dice qué modelo contestó y por qué se derivó |
| `service/observability.py` | registro y métricas | registrar **nunca** puede tumbar una decisión |
| `service/schemas.py` | contrato HTTP | compatible con versiones anteriores: sólo se agregan campos |

## El contrato

```jsonc
POST /decide
{ "state": "el texto a decidir",
  "questions": [ { "id": "s", "type": "noul", "instructions": "¿Es positivo?" } ],
  "model": null }          // opcional: fija el modelo y salta el enrutamiento (para comparar)
```

```jsonc
{ "model": "cardiff-xlmr", "latency_ms": 57.6,
  "answers": [{
    "id": "s", "type": "noul", "value": true, "model_used": "cardiff-xlmr",
    "confidence": 0.768, "raw_confidence": 0.768,
    "calibrated": false, "temperature": null,
    "calibration_note": "no temperature for 'noul' (no calibration file)",
    "neutral_mass": 0.81, "probs": [0.232, 0.768], "threshold": 0.75,
    "delegate_to_cloud": true, "delegate_reason": "high_neutral_mass(0.809>0.7)",
    "supported": true, "truncated": false, "input_tokens": 21, "max_length": 512 }] }
```

Tres primitivas, tomadas del motor de decisión que este harness integra:

| Primitiva | Pregunta | Respuesta |
|---|---|---|
| `noul` | ¿se cumple esta afirmación? | booleano + P(verdadero) |
| `choice` | ¿cuál de estas opciones? | opción + distribución |
| `score` | ¿cuánto, en esta escala? | nivel + distribución (+ valor numérico) |


## Adaptadores

| Adaptador | Sirve | Requisitos |
|---|---|---|
| `coreml` | Paquetes CoreML de Laya (`model.mlpackage` + `weight.bin`), ANE/GPU | `laya-coreml` |
| `laya` | Checkpoints Laya en safetensors, sin CoreML (x86/Linux/CI) | `laya` + `torch` |
| `transformers` | Clasificadores de Hugging Face; para 3 clases se reduce a binario con `binary_reduction` (ahí se descarta la masa neutral, que es lo que compensa la compuerta de masa neutral) | `torch` + `transformers` |

Ojo: `laya-coreml` y `laya` **no comparten el esquema de pregunta** (`type`/`instructions` contra
`t`/`ins`). El adaptador traduce; no se asume una forma común.

## Enrutamiento por primitiva

Cada primitiva puede servirse con **un modelo distinto**: es lo que permite tener sentimiento
fine-tuneado y un motor de decisión general en el mismo servicio, sin que el cliente sepa cuál es
cuál.

```yaml
routing:
  noul: cardiff-xlmr      # sentimiento
  choice: laya-base       # motor general zero-shot
  score: laya-base
preload: [cardiff-xlmr, laya-base]
```

Si el modelo de turno no declara soportar una primitiva, la respuesta vuelve como
`unsupported_by_model` y se deriva: **nunca se inventa una respuesta**. `preload` importa porque
cargar un modelo tarda segundos y el timeout del cliente puede ser más corto.

## La política de derivación

Se deriva si pasa **cualquiera** de estas tres cosas, y la razón queda escrita en la respuesta:

| Condición | Por qué | Medido en |
|---|---|---|
| confianza calibrada < umbral por primitiva | el modelo duda | `results/SUMMARY_HARNESS_TEST.md` |
| `P(neutro)` > `neutral_mass_threshold` | el texto no tiene sentimiento que clasificar | ídem |
| el texto no entró en la ventana del modelo | no vio todo el texto: su seguridad no vale | ídem |
| el modelo no soporta esa primitiva | no puede contestarla | — |

**El servicio marca la derivación, no la ejecuta.** No tiene credenciales de cloud ni SDK de ningún
proveedor: responde con `delegate_to_cloud` y un motivo legible en vez de caer en silencio al
resultado local. Hacer la llamada al cloud es trabajo del cliente: `examples/delegate.py` la hace
contra cualquier endpoint compatible con OpenAI, y `make delegate TEXT="..."` lo corre.

## Garantías de diseño

1. **El hash manda.** Si el sha256 real de los pesos no coincide con `expect_sha256`, ese modelo no
   se carga y el servicio lo dice. Nació de un incidente real: el servicio desplegado estaba
   sirviendo **otro modelo** del que la documentación decía.
2. **`calibrated` no miente.** Es verdadero sólo si se aplicó una temperatura a esa respuesta. Antes
   significaba "hay un archivo de calibración", que es otra cosa.
3. **Serialización de la inferencia.** MPS/Metal no es thread-safe: sin candado, **dos peticiones
   simultáneas abortaban el proceso**. Ver `docs/OPERATIONS.md`.
4. **El registro no puede tumbar una decisión.** Va en `try/except` y cuenta sus propios errores.
5. **Lo que no se sabe, se declara.** Primitiva no soportada, texto truncado, confianza cruda:
   todo viaja en la respuesta en vez de quedar implícito.

## Ver también

- `docs/DECISIONS.md` — cada decisión con la evidencia que la sostiene.
- `docs/OPERATIONS.md` — cómo se despliega, se observa y se cambia.
- `results/SUMMARY_*.md` — las mediciones, con su método.

</details>
