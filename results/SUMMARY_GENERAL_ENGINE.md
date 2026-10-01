# The general engine, restored, and what it measures

The V7 service routes each primitive to a different model. Right now:

| Primitive | Model | Why |
|---|---|---|
| `noul` (sentiment) | `cardiff-xlmr` | the best measured: 91.67% on the 240-text sample |
| `choice` (classify/pick) | `laya-base` | general zero-shot engine |
| `score` (urgency/scale) | `laya-base` | same |

A single HTTP call can carry all three, and every answer says which model produced it (`model_used`).
Measured against the deployed service:

| Question | Model | Answer | Confidence | Delegates? |
|---|---|---|---|---|
| Positive sentiment? (`noul`) | `cardiff-xlmr` | `false` | 0.9693 | no |
| Which team should handle it? (`choice`) | `laya-base` | `billing` | 0.9965 | no |
| How urgent is it? (`score`) | `laya-base` | `media` | 0.4862 | **yes** (threshold 0.70) |

## The formulation matters more than the model

Same engine (`laya-base`), same task (sentiment), same 240-text sample:

| Formulation | Accuracy | Mean confidence | Median latency |
|---|---|---|---|
| `choice` with options [positive, negative] | **87.50%** | 0.9338 | 19 ms |
| `noul` ("does it express positive sentiment?") | **53.33%** | 0.9632 | 18 ms |

The 53.33% is not noise: on six control texts (three clearly positive, three clearly negative) the
model **answered `false` to all six** with P(true) between 0.00 and 0.25 — including "I love this
product, it changed my life!". Since the sample is balanced, always answering "no" yields ~50%. With
the `choice` formulation it gets all six right at probability 1.00.

The honest reading: the base model **does not answer that particular question well in noul format**,
most likely because the phrasing does not resemble what it saw during training. The fine-tuned models
(v1, v2) do, because they were trained on exactly that phrasing. It is not an adapter problem: it was
checked against the model's raw output.

## Comparison on the same sample (240 texts, 80 per language)

| Model | Formulation | Accuracy | Local accuracy | Local coverage |
|---|---|---|---|---|
| `cardiff-xlmr` | noul | **91.67%** | 95.28% | 88% |
| `laya-base` (zero-shot) | choice | **87.50%** | 88.84% | 93% |
| `laya-sentiment-v1` (fine-tune) | noul | 84.58% | 89.35% | 90% |
| `laya-sentiment-v2` (fine-tune, 4.8x) | noul | 83.75% | 85.17% | 98% |
| `laya-base` (zero-shot) | noul | 53.33% | 53.28% | 95% |

**A zero-shot general engine, with no training at all, beats this project's fine-tuned model at the
same task** (87.5% against 84.6% on this sample). It is the same conclusion the data-vs-recipe
isolation reached, now with different evidence: the fine-tune was not contributing what it was
believed to contribute.

## The cost of lazy loading

The general model takes ~2.7 s to load and the DSH plugin times out at 2.5 s: with lazy loading, the
first `choice` question would have failed on timeout. That is why `preload` includes both models that
serve a primitive. Warm, latency is ~19-26 ms per question.

## How to verify

```bash
curl -s http://127.0.0.1:8090/health | python3 -m json.tool   # routing and per-model state
curl -s -X POST http://127.0.0.1:8090/selftest | python3 -m json.tool   # all 5 models
python scripts/battery_choice.py --type choice --options positive,negative
python scripts/battery_choice.py --type noul --model laya-base   # pins the model, skips routing
```

---

<details>
<summary><h2>🇪🇸 Versión en Español — Haz clic aquí para desplegar</h2></summary>

# El motor general restaurado, y lo que mide

El servicio V7 enruta cada primitiva a un modelo distinto. Ahora mismo:

| Primitiva | Modelo | Por qué |
|---|---|---|
| `noul` (sentimiento) | `cardiff-xlmr` | el mejor medido: 91,67 % en la muestra de 240 |
| `choice` (clasificar/elegir) | `laya-base` | motor general zero-shot |
| `score` (urgencia/escala) | `laya-base` | ídem |

Una sola llamada HTTP puede llevar las tres, y cada respuesta dice con qué modelo se contestó
(`model_used`). Medido contra el servicio desplegado:

| Pregunta | Modelo | Respuesta | Confianza | ¿Deriva? |
|---|---|---|---|---|
| ¿Sentimiento positivo? (`noul`) | `cardiff-xlmr` | `false` | 0,9693 | no |
| ¿Qué equipo debe atenderlo? (`choice`) | `laya-base` | `billing` | 0,9965 | no |
| ¿Qué urgencia tiene? (`score`) | `laya-base` | `media` | 0,4862 | **sí** (umbral 0,70) |

## La formulación importa más que el modelo

Mismo motor (`laya-base`), misma tarea (sentimiento), misma muestra de 240 textos:

| Formulación | Accuracy | Confianza media | Latencia mediana |
|---|---|---|---|
| `choice` con opciones [positive, negative] | **87,50 %** | 0,9338 | 19 ms |
| `noul` ("¿expresa sentimiento positivo?") | **53,33 %** | 0,9632 | 18 ms |

El 53,33 % no es ruido: en seis textos de control (tres claramente positivos, tres claramente
negativos) el modelo **contestó `false` a los seis** con P(true) entre 0,00 y 0,25 — incluido
"I love this product, it changed my life!". Como la muestra está balanceada, responder siempre "no"
da ~50 %. Con la formulación `choice`, esos mismos seis los acierta todos con probabilidad 1,00.

La lectura honesta: el modelo base **no responde bien esa pregunta concreta en formato noul**, muy
probablemente porque la fraseo no se parece a lo que vio durante su entrenamiento. Los modelos
fine-tuneados (v1, v2) sí, porque se entrenaron exactamente con ese fraseo. No es un problema del
adaptador: se verificó contra la respuesta cruda del modelo.

## Comparación en la misma muestra (240 textos, 80 por idioma)

| Modelo | Formulación | Accuracy | Accuracy local | Cobertura local |
|---|---|---|---|---|
| `cardiff-xlmr` | noul | **91,67 %** | 95,28 % | 88 % |
| `laya-base` (zero-shot) | choice | **87,50 %** | 88,84 % | 93 % |
| `laya-sentiment-v1` (fine-tune) | noul | 84,58 % | 89,35 % | 90 % |
| `laya-sentiment-v2` (fine-tune 4,8×) | noul | 83,75 % | 85,17 % | 98 % |
| `laya-base` (zero-shot) | noul | 53,33 % | 53,28 % | 95 % |

**Un motor general zero-shot, sin ningún entrenamiento, supera al modelo fine-tuneado de este
proyecto en la misma tarea** (87,5 % contra 84,6 % en esta muestra). Es la misma conclusión que dio
el aislamiento dato/receta, ahora con otra evidencia: el fine-tune no aportaba lo que se creía.

## Coste de la carga perezosa

El modelo general tarda ~2,7 s en cargar y el plugin de DSH corta a 2,5 s: con carga perezosa, la
primera pregunta de tipo `choice` habría fallado por timeout. Por eso `preload` incluye los dos
modelos que sirven alguna primitiva. En caliente, la latencia es ~19-26 ms por pregunta.

## Cómo se verifica

```bash
curl -s http://127.0.0.1:8090/health | python3 -m json.tool   # routing y estado por modelo
curl -s -X POST http://127.0.0.1:8090/selftest | python3 -m json.tool   # los 5 modelos
python scripts/battery_choice.py --type choice --options positive,negative
python scripts/battery_choice.py --type noul --model laya-base   # fija el modelo, salta el routing
```

</details>
