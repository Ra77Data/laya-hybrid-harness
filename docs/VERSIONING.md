# Versioning V7 — model-agnostic decision service

## Date: 2026-09-30

## Why it exists

V7 does not add a model: it fixes the **deployment**. Auditing the harness that was running surfaced
four problems that no earlier version detected:

| Problem found | What V7 does |
|---|---|
| Port 8090 was held by the **V3** service (the PoC model, `587e4ac8…`), while the documentation said V5 was deployed with the validated model | The model comes from `config.yaml`; `/health` reports the **sha256 of the weights file** and whether it matches the expected one. If it does not match, it **does not start** |
| `calibrated: true` meant "a calibration file exists", not "a temperature was applied" | `calibrated` is true only if a T was applied; the answer carries `temperature` and, when it could not be applied, `calibration_note` |
| The delegation policy only applied to `choice`: sentiment (`noul`) never delegated | It applies to every primitive, with per-type thresholds, on calibrated confidence |
| The service did not distinguish what it cannot do | Every model declares `supports`; anything else comes back as `unsupported_by_model` |

## Architecture

```
DSH Cordis plugin  ->  POST /decide  ->  V7 service  ->  adapter  ->  model
   (unchanged)         127.0.0.1:8090    config.yaml    coreml | laya | transformers
```

The DSH plugin **is not touched**: it points at `http://127.0.0.1:8090` by default, so replacing the
service behind the port is the entire change.

## Models in the registry

| id | adapter | measured accuracy (240 texts) | local accuracy | median latency |
|---|---|---|---|---|
| `cardiff-xlmr` | transformers | **91.67%** | **95.28%** over 88% of traffic | **10 ms** |
| `laya-sentiment-v1` | coreml | 84.58% | 89.35% over 90% | 55 ms |
| `laya-sentiment-v2` | laya | 83.75% | 85.17% over 98% | 19 ms |

**Active: `cardiff-xlmr`.** The measurement shows it wins on accuracy, on the quality of what it
answers locally and on latency, without needing calibration. On the sarcasm case it gets it wrong at
0.68 confidence and **delegates**, while v1 got it wrong at 0.91 and answered locally: the gate works
better with it.

## Status

- Deployed in its own directory (the code in this repository), port 8090.
- Replaces the V3 service. **V3 is archived, not deleted.**
- V5 keeps the validated CoreML model, which V7 serves through the `coreml` adapter.

## Routing by primitive (general engine restored)

After switching to serving a sentiment model, the DSH tool had been left with **only** `noul`: a
`choice` or `score` question came back as `unsupported_by_model`. The general decision engine was
restored without going back to a hardcoded model: `routing` in `config.yaml` decides which model
handles each primitive, and the service loads models lazily.

- `noul` -> `cardiff-xlmr` (sentiment, 91.67% on 240 texts)
- `choice` / `score` -> `laya-base` (general zero-shot engine)

Full registry: 5 models (`cardiff-xlmr`, `laya-base`, `laya-sentiment-v1`, `laya-sentiment-v2`,
`laya-poc`), all with a verified real sha256 and their own self-test case. `/selftest` runs the 7
cases and passes.

Two honesty fixes that came out of this:

- A Hugging Face cache **blob name is not** the sha256 of the content (verified on two models). The
  service was reporting the former as `sha256`; it now hashes the real file.
- The adapter **fabricated** a probability vector when the backend exposed no distribution. It now
  returns an empty `probs` and the model's own confidence, marked as uncalibrated.

And a behavioural finding: the **formulation** (primitive and phrasing) matters more than the model.
`laya-base` scores 87.5% asking for sentiment as `choice` and 53.3% as `noul`.

## Testing the harness (edge cases and concurrency)

Two real failures, found by testing the deployed service, and fixed:

1. **MPS is not thread-safe**: two concurrent requests aborted the process with a Metal assertion
   (`MTLCommandBufferStatusCommitted`). Fixed with a global inference lock; verified up to 16
   concurrent requests (16/16, no restarts).
2. **Silent truncation**: the Hugging Face adapter cut at 128 tokens (a hardcoded value), so a
   2,489-character text was classified the wrong way at 0.908 confidence and not delegated. Now
   `max_length` is configurable (512), the answer reports truncation and **truncating forces
   delegation**.

Also: the evaluation scripts now carry their own `data/test_extended.jsonl` instead of depending on
the workspace path.

## Neutral-mass policy

A neutral text came back positive at 0.768 and did not delegate: Cardiff's binary reduction cannot say
"neutral". The policy now delegates when `P(neutral)` exceeds `delegation.neutral_mass_threshold`.

The threshold (0.70) was chosen with data: 600 real neutral texts from class 1 of the original dataset
against the 1,740 non-neutral ones. AUC 0.81; at 0.70 it detects 32.7% of neutrals for +3.9 points of
traffic. 0.50 was rejected: it detects more neutrals but costs four times the traffic at the same
local error. Details in `results/SUMMARY_HARNESS_TEST.md`.

## Observability

Every decision is logged to daily JSONL (`logs/decisions/`), with a configurable detail level
(`off`/`metadata`/`excerpt`/`full`; **default now `metadata`: no text**). It records which model
answered, raw and calibrated confidence, the temperature applied, the neutral mass, whether the text
was truncated and **why it was delegated**, with the reason grouped by kind.

Two tools: `scripts/report_decisions.py` (readable report) and `scripts/export_eval.py` (exports real
traffic for labelling, so accuracy can be measured on your own traffic).

Logging runs inside a `try/except`: **it cannot take down a decision**. Verified with 83 records and
0 errors.

Along the way, the log path was fixed to resolve against the config's directory rather than the
current one, which used to make the scripts return zero records when called from elsewhere.

## Pending

- [x] ~~Observability~~: daily JSONL logging with a configurable detail level, `/metrics` with
      delegation by primitive and by reason, a CLI report and an exporter for labelling real traffic.
      83 records written, 0 errors.
- [x] ~~Persistent startup (launchd) instead of `nohup`~~: LaunchAgent installed, with automatic
      restart verified (`kill -9` → `runs` 1→2) and a cold start verified.
- [x] ~~`choice`/`score` on the CoreML/Laya adapters~~: tested on both adapters, with
      `probabilities`/`legend` read correctly.
- [x] ~~Re-measure CoreML latency~~: measured **with the same method V5 used** (timing `/decide` on
      the server, which is what its `server.py` does). It gives **55 ms** median end to end and
      **50 ms** of direct inference without HTTP over 30 calls, so HTTP overhead is ~5 ms and the
      "16 ms steady" **does not reproduce**: it is the model, not the network. There is no record of
      how that number was obtained, so the discrepancy is documented rather than resolved.
      See `results/SUMMARY_BATTERY.md`.

---

<details>
<summary><h2>🇪🇸 Versión en Español — Haz clic aquí para desplegar</h2></summary>

# Versionado V7 — Servicio de decisión agnóstico del modelo

## Fecha: 2026-09-30

## Por qué existe

V7 no agrega un modelo: arregla el **despliegue**. Auditando el harness que estaba corriendo
aparecieron cuatro problemas que ninguna versión anterior detectaba:

| Problema encontrado | Qué hace V7 |
|---|---|
| El puerto 8090 lo ocupaba el servicio de **V3** (modelo del PoC, `587e4ac8…`), mientras la documentación decía que estaba desplegado V5 con el modelo validado | El modelo sale de `config.yaml`; `/health` reporta el **sha256 del archivo de pesos** y si coincide con el esperado. Si no coincide, **no arranca** |
| `calibrated: true` significaba "hay un archivo de calibración", no "se aplicó una temperatura" | `calibrated` es verdadero solo si se aplicó una T; la respuesta trae `temperature` y, si no se pudo, `calibration_note` |
| La política de derivación solo aplicaba a `choice`: el sentimiento (`noul`) nunca delegaba | Aplica a todas las primitivas, con umbral por tipo, sobre confianza calibrada |
| El servicio no distinguía lo que no sabe hacer | Cada modelo declara `supports`; lo demás vuelve como `unsupported_by_model` |

## Arquitectura

```
plugin Cordis de DSH  ->  POST /decide  ->  servicio V7  ->  adaptador  ->  modelo
   (sin cambios)          127.0.0.1:8090      config.yaml     coreml | laya | transformers
```

El plugin de DSH **no se toca**: apunta a `http://127.0.0.1:8090` por defecto, así que reemplazar el
servicio detrás del puerto es todo el cambio.

## Modelos del registro

| id | adaptador | accuracy medida (240 textos) | accuracy local | latencia mediana |
|---|---|---|---|---|
| `cardiff-xlmr` | transformers | **91,67 %** | **95,28 %** sobre 88 % del tráfico | **10 ms** |
| `laya-sentiment-v1` | coreml | 84,58 % | 89,35 % sobre 90 % | 55 ms |
| `laya-sentiment-v2` | laya | 83,75 % | 85,17 % sobre 98 % | 19 ms |

**Activo: `cardiff-xlmr`.** La medición muestra que gana en precisión, en calidad de lo que responde
localmente y en latencia, sin necesitar calibración. Además, en el caso de sarcasmo se equivoca con
0,68 de confianza y **deriva**, mientras v1 se equivoca con 0,91 y responde local: la compuerta
funciona mejor con él.

## Estado

- Desplegado en su propio directorio (el código de este repositorio), puerto 8090.
- Reemplaza al servicio de V3. **V3 queda archivado, no borrado.**
- V5 conserva el modelo CoreML validado, que V7 sirve a través del adaptador `coreml`.

## Enrutamiento por primitiva (motor general restaurado)

Al pasar a servir un modelo de sentimiento, la tool de DSH había quedado **sólo** con `noul`: una
pregunta de tipo `choice` o `score` volvía como `unsupported_by_model`. Se restauró el motor de
decisión general sin volver a un modelo cableado: `routing` en `config.yaml` decide qué modelo
atiende cada primitiva, y el servicio carga los modelos de forma perezosa.

- `noul` -> `cardiff-xlmr` (sentimiento, 91,67 % en 240 textos)
- `choice` / `score` -> `laya-base` (motor general zero-shot)

Registro completo: 5 modelos (`cardiff-xlmr`, `laya-base`, `laya-sentiment-v1`, `laya-sentiment-v2`,
`laya-poc`), todos con sha256 real verificado y caso de self-test propio. `/selftest` corre los 7
casos y pasa.

Dos correcciones de honestidad que salieron de esto:

- El **nombre del blob** de la caché de Hugging Face **no es** el sha256 del contenido (verificado
  para dos modelos). El servicio reportaba aquel como `sha256`; ahora hashea el archivo real.
- El adaptador **fabricaba** un vector de probabilidades cuando el backend no exponía distribución.
  Ahora devuelve `probs` vacío y la confianza propia del modelo, marcada como no calibrada.

Y un hallazgo de comportamiento: la **formulación** (primitiva y fraseo) pesa más que el modelo.
`laya-base` acierta 87,5 % preguntando el sentimiento como `choice` y 53,3 % como `noul`.

## Prueba del harness (casos límite y concurrencia)

Dos fallos reales, encontrados probando el servicio desplegado y corregidos:

1. **MPS no es thread-safe**: dos peticiones simultáneas abortaban el proceso con una aserción de
   Metal (`MTLCommandBufferStatusCommitted`). Arreglado con un candado global de inferencia;
   verificado hasta 16 concurrentes (16/16, sin reinicios).
2. **Truncación silenciosa**: el adaptador de Hugging Face cortaba a 128 tokens (valor hardcodeado),
   así que un texto de 2.489 caracteres se clasificaba al revés con 0,908 de confianza y sin
   derivar. Ahora `max_length` es configurable (512), la respuesta reporta la truncación y
   **truncar obliga a derivar**.

Además: las baterías ahora llevan su propio `data/test_extended.jsonl` en vez de depender de la ruta
del workspace.

## Política de masa neutral

Un texto neutro salía positivo con 0,768 y sin derivar: la reducción binaria de Cardiff no sabe decir
"neutro". Ahora la política deriva cuando `P(neutro)` supera `delegation.neutral_mass_threshold`.

El umbral (0,70) se eligió con datos: 600 neutros reales de la clase 1 del dataset original contra
los 1.740 no neutros. AUC 0,81; con 0,70 se detecta el 32,7 % de los neutros por +3,9 puntos de
tráfico. Se descartó 0,50, que detecta más neutros pero cuesta cuatro veces más tráfico con el mismo
error local. Detalle en `results/SUMMARY_HARNESS_TEST.md`.

## Observabilidad

Cada decisión se registra en JSONL por día (`logs/decisions/`), con nivel de detalle configurable
(`off`/`metadata`/`excerpt`/`full`; **ahora por defecto `metadata`: sin texto**). Se guarda qué
modelo contestó, la confianza cruda y la calibrada, la temperatura aplicada, la masa neutral, si se
truncó y **por qué se derivó**, con el motivo agrupado en su tipo.

Dos herramientas: `scripts/report_decisions.py` (informe legible) y `scripts/export_eval.py`
(exporta tráfico real para etiquetar y poder medir precisión sobre tráfico propio).

El registro va en un `try/except`: **no puede tumbar una decisión**. Verificado con 83 registros y 0
errores.

De paso se corrigió que la ruta del registro se resolvía contra el directorio actual y no contra el
del config, así que los scripts devolvían cero registros si se los llamaba desde otro sitio.

## Pendiente

- [x] ~~Observabilidad~~: registro JSONL por día con nivel de detalle configurable, `/metrics` con
      derivación por primitiva y por motivo, informe CLI y exportador de tráfico real para etiquetar.
      83 registros escritos, 0 errores.
- [x] ~~Arranque persistente (launchd) en lugar de `nohup`~~: LaunchAgent instalado, con
      reinicio automático verificado (`kill -9` → `runs` 1→2) y arranque en frío verificado.
- [x] ~~Camino `choice`/`score` sobre los adaptadores CoreML/Laya~~: probado en los dos adaptadores,
      con `probabilities`/`legend` leídos correctamente.
- [x] ~~Re-medir la latencia del camino CoreML~~: medido **con el mismo método que usaba V5**
      (cronometrar `/decide` en el servidor, que es lo que hace su `server.py`). Da **55 ms** de mediana
      de punta a punta y **50 ms** de inferencia directa sin HTTP en 30 llamadas, así que el overhead de
      HTTP son ~5 ms y el "16 ms steady" **no se reproduce**: es el modelo, no la red. No queda registro
      de cómo se obtuvo aquel número, así que la discrepancia se documenta en vez de resolverse.
      Ver `results/SUMMARY_BATTERY.md`.

</details>
