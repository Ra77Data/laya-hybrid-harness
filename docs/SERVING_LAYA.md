# Serving Laya beyond Apple Silicon

## Why this page exists

Laya's intended path is CoreML on the Neural Engine, and that is the fast one. It is also
**Apple-Silicon-only**, which leaves out Linux, Windows, x86 machines and CI — and the decision engine
itself has no such requirement: `laya.agent.load()` reads a safetensors checkpoint and runs on CPU or
MPS, anywhere PyTorch runs.

This page documents that portable path with what was actually measured while building the harness in
this repository. It is written for people using Laya, not for people using this harness: the first
section needs nothing from here.

## The short version

```bash
pip install laya torch          # no laya-coreml, no macOS
```

```python
import laya.agent

agent = laya.agent.load("convaiinnovations/laya-multilingual")   # ~2.7 s, then cached

print(agent.predict(
    "El pedido llegó el martes.",
    {"s": {"type": "noul", "instructions": "Does this text express positive sentiment?"}}))
```

The `noul` answer comes back like this (real output, macOS + MPS; on CPU it is slower and identical in
shape):

```json
{"model": "laya-rl-agent",
 "answers": {"s": {"type": "noul", "noul": 0.0, "confidence": 1.0, "answer_confidence": 1.0,
                   "action": {"act_probability": 1.0}}},
 "usage": {"input_tokens": 39, "output_tokens": 0, "state_tokens": 6,
           "state_tokens_dropped": 0, "truncated": false, "truncated_questions": []}}
```

The same engine asked as `choice`:

```python
agent.predict("El pedido llegó el martes.",
              {"c": {"type": "choice", "criteria": ["positive", "negative"],
                     "instructions": "Is the sentiment of this text positive or negative?"}})
```

```json
{"answers": {"c": {"type": "choice", "choice": "negative",
                   "probabilities": {"positive": 0.3488, "negative": 0.6512},
                   "confidence": 0.067, "answer_confidence": 0.6512}}}
```

## Three things about the raw answer worth knowing

1. **`confidence` and `answer_confidence` are not the same field.** In the example above the model
   answers with 0.6512 of probability mass but reports `confidence: 0.067`. If you build a threshold
   on the wrong one you will delegate (or accept) the opposite of what you meant. Decide explicitly
   which quantity your policy is about — the harness ended up making a service-wide contract out of
   that distinction, and it is the single most useful thing we learned here.
2. **The distribution is not always a list.** `choice` publishes `probabilities` as an
   option-to-probability dict; `score` indexes it by number and carries the labels in `legend`. A
   generic "read probs" helper will silently see nothing.
3. **`usage` is not decoration.** `state_tokens_dropped` and `truncated` tell you that the model never
   read the whole input. Discarding them is how you end up with a confident answer about half a
   ticket.

## The finding that matters most: the formulation beats the model

Same engine, same task (sentiment), same 240 labelled texts, only the way the question is asked
changes:

| Formulation | Accuracy | Mean confidence | Median latency |
|---|---|---|---|
| `choice` with `criteria: [positive, negative]` | **87.50%** | 0.9338 | 19 ms |
| `noul` ("does this text express positive sentiment?") | **53.33%** | 0.9632 | 18 ms |

The 53.33% is not noise. On six control texts (three clearly positive, three clearly negative) the
model **answered `false` to all six** in the `noul` formulation, with P(true) between 0.00 and 0.25 —
including *"I love this product, it changed my life!"*. Since the sample is balanced, always answering
"no" scores ~50%.

The honest reading: **the base model does not answer that particular phrasing well**, most likely
because it does not resemble what it saw during training. A fine-tune trained on exactly that phrasing
does (`noul` is the right primitive for the models fine-tuned for it). If you are using the base model
zero-shot, formulate as `choice` and give it the labels as criteria.

## Latency: the portable path is fast enough

From the same battery, all through the same HTTP service, medians on short texts (240 texts):

| Path | Adapter | Median |
|---|---|---|
| safetensors, MPS | `laya` | **19 ms** |
| CoreML FP16, ANE | `coreml` | 55 ms |

**Read that table carefully: it is not a fair backend comparison.** The two entries are different
fine-tunes (different training data, different size), served by different adapters, so the difference
cannot be attributed to CoreML versus safetensors. What the measurement does support is the claim this
page is about: **the portable path is usable at interactive latency without the Neural Engine.**

For completeness, a number that did not reproduce: the CoreML path was documented at "16 ms steady" in
an earlier version of the pipeline. Re-measured with the same method it gives 50-55 ms. It was the
model, not the network — the discrepancy is documented in
[`../results/SUMMARY_BATTERY.md`](../results/SUMMARY_BATTERY.md) rather than resolved.

## If you want the service built around it

The harness that produced these measurements is in this repository (Apache-2.0, same license as Laya).
It adds, on top of the agent: routing by primitive (a different model per `noul` / `choice` / `score`
behind one endpoint), an honest confidence contract (`calibrated` is true only if a temperature was
actually applied), a delegation policy with a neutral-mass gate, and JSONL observability.

```bash
make setup-full    # any OS; the CoreML adapter stays optional
make demo
```

Its own documentation starts at [`ARCHITECTURE.md`](ARCHITECTURE.md), and the measured results —with
their limits— are in [`../results/`](../results/).

## What this page does not claim

- **Not a benchmark of Laya against anything.** One task, one dataset, one wrapper.
- **Not a claim that CoreML is unnecessary.** On Apple Silicon, with a model converted for the ANE and
  a workload where the conversion is tuned, it may well win. This page only says the portable path
  works, and gives the numbers we have.
- **Not measured on Linux.** The measurements above ran on macOS with MPS. The code path has no
  platform-specific branch — `laya` + `torch` — but if you run it on x86 or in CI, measure your own
  latencies rather than quoting these.
- **The base model is zero-shot.** The accuracy figures for sentiment come from one comparison on one
  dataset; they are evidence about *formulation*, not a quality claim about Laya.

---

<details>
<summary><h2>🇪🇸 Versión en Español — Haz clic aquí para desplegar</h2></summary>

# Servir Laya fuera de Apple Silicon

## Por qué existe esta página

El camino previsto de Laya es CoreML sobre el Neural Engine, y es el rápido. También es **exclusivo de
Apple Silicon**, lo que deja afuera Linux, Windows, las máquinas x86 y CI — y el motor de decisión no
tiene ese requisito: `laya.agent.load()` lee un checkpoint en safetensors y corre en CPU o MPS, en
cualquier lugar donde corra PyTorch.

Esta página documenta ese camino portátil con lo que efectivamente se midió al construir el harness de
este repositorio. Está escrita para quien usa Laya, no para quien usa este harness: la primera sección
no necesita nada de acá.

## La versión corta

```bash
pip install laya torch          # sin laya-coreml, sin macOS
```

```python
import laya.agent

agent = laya.agent.load("convaiinnovations/laya-multilingual")   # ~2,7 s, después queda en caché

print(agent.predict(
    "El pedido llegó el martes.",
    {"s": {"type": "noul", "instructions": "Does this text express positive sentiment?"}}))
```

La respuesta de `noul` vuelve así (salida real, macOS + MPS; en CPU es más lenta e idéntica en forma):

```json
{"model": "laya-rl-agent",
 "answers": {"s": {"type": "noul", "noul": 0.0, "confidence": 1.0, "answer_confidence": 1.0,
                   "action": {"act_probability": 1.0}}},
 "usage": {"input_tokens": 39, "output_tokens": 0, "state_tokens": 6,
           "state_tokens_dropped": 0, "truncated": false, "truncated_questions": []}}
```

El mismo motor preguntado como `choice`:

```python
agent.predict("El pedido llegó el martes.",
              {"c": {"type": "choice", "criteria": ["positive", "negative"],
                     "instructions": "Is the sentiment of this text positive or negative?"}})
```

```json
{"answers": {"c": {"type": "choice", "choice": "negative",
                   "probabilities": {"positive": 0.3488, "negative": 0.6512},
                   "confidence": 0.067, "answer_confidence": 0.6512}}}
```

## Tres cosas de la respuesta cruda que conviene saber

1. **`confidence` y `answer_confidence` no son el mismo campo.** En el ejemplo de arriba el modelo
   responde con 0,6512 de masa pero reporta `confidence: 0.067`. Si construís un umbral sobre el campo
   equivocado vas a derivar (o aceptar) lo contrario de lo que querías. Decidí explícitamente sobre qué
   cantidad habla tu política: el harness terminó haciendo de esa distinción un contrato de todo el
   servicio, y es lo más útil que aprendimos acá.
2. **La distribución no siempre es una lista.** `choice` publica `probabilities` como un dict
   opción→probabilidad; `score` lo indexa por número y lleva las etiquetas en `legend`. Un helper
   genérico de "leer probs" no va a ver nada, en silencio.
3. **`usage` no es decoración.** `state_tokens_dropped` y `truncated` dicen que el modelo no leyó todo
   el texto. Descartarlos es cómo terminás con una respuesta segura sobre medio ticket.

## El hallazgo que más importa: la formulación le gana al modelo

Mismo motor, misma tarea (sentimiento), mismos 240 textos etiquetados, y lo único que cambia es cómo se
pregunta:

| Formulación | Accuracy | Confianza media | Latencia mediana |
|---|---|---|---|
| `choice` con `criteria: [positive, negative]` | **87,50 %** | 0,9338 | 19 ms |
| `noul` ("¿expresa sentimiento positivo?") | **53,33 %** | 0,9632 | 18 ms |

El 53,33 % no es ruido. Sobre seis textos de control (tres claramente positivos, tres claramente
negativos) el modelo **contestó `false` a los seis** en la formulación `noul`, con P(true) entre 0,00 y
0,25 — incluido *"I love this product, it changed my life!"*. Como la muestra está balanceada,
responder siempre "no" saca ~50 %.

La lectura honesta: **el modelo base no responde bien a ese fraseo concreto**, muy probablemente porque
no se parece a lo que vio durante su entrenamiento. Un fine-tune entrenado exactamente con ese fraseo sí
(`noul` es la primitiva correcta para los modelos ajustados para eso). Si estás usando el modelo base
zero-shot, formulá como `choice` y dale las etiquetas como criterios.

## Latencia: el camino portátil alcanza

De la misma batería, todo a través del mismo servicio HTTP, medianas en textos cortos (240 textos):

| Camino | Adaptador | Mediana |
|---|---|---|
| safetensors, MPS | `laya` | **19 ms** |
| CoreML FP16, ANE | `coreml` | 55 ms |

**Leé esa tabla con cuidado: no es una comparación justa de backends.** Las dos entradas son
fine-tunes distintos (distintos datos de entrenamiento, distinto tamaño), servidos por adaptadores
distintos, así que la diferencia no se puede atribuir a CoreML contra safetensors. Lo que sí sostiene
la medición es la afirmación de esta página: **el camino portátil es usable a latencia interactiva sin
el Neural Engine.**

Para completar, un número que no reprodujo: el camino CoreML estaba documentado como "16 ms estable" en
una versión anterior del pipeline. Re-medido con su mismo método da 50-55 ms. Era el modelo, no la red:
la discrepancia está documentada en
[`../results/SUMMARY_BATTERY.md`](../results/SUMMARY_BATTERY.md) en vez de resuelta.

## Si querés el servicio armado alrededor

El harness que produjo estas mediciones está en este repositorio (Apache-2.0, la misma licencia que
Laya). Agrega, sobre el agente: enrutamiento por primitiva (un modelo distinto por `noul` / `choice` /
`score` detrás de un solo endpoint), un contrato de confianza honesto (`calibrated` es verdadero sólo
si se aplicó una temperatura de verdad), una política de derivación con compuerta de masa neutral, y
observabilidad en JSONL.

```bash
make setup-full    # cualquier SO; el adaptador CoreML queda opcional
make demo
```

Su documentación arranca en [`ARCHITECTURE.md`](ARCHITECTURE.md), y los resultados medidos —con sus
límites— están en [`../results/`](../results/).

## Lo que esta página NO afirma

- **No es un benchmark de Laya contra nada.** Una tarea, un dataset, un wrapper.
- **No afirma que CoreML sea innecesario.** En Apple Silicon, con un modelo convertido para el ANE y
  una carga donde la conversión esté afinada, puede ganar. Esta página sólo dice que el camino portátil
  funciona, y da los números que tenemos.
- **No está medido en Linux.** Las mediciones de arriba corrieron en macOS con MPS. El camino de código
  no tiene ninguna rama por plataforma —`laya` + `torch`—, pero si lo corrés en x86 o en CI, medí tus
  propias latencias en vez de citar estas.
- **El modelo base es zero-shot.** Las cifras de accuracy para sentimiento salen de una comparación
  sobre un dataset; son evidencia sobre la *formulación*, no una afirmación de calidad sobre Laya.

</details>
