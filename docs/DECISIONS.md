# Decisions and their evidence

Every design decision in this harness, with the data that supports it. None of these is an aesthetic
preference: each one came out of an incident or a measurement.

## 1. The model is configuration, not code

**Why.** The deployed harness was serving **a different model** than the documentation claimed: the
port was held by an old version with a fine-tune for another task, and nothing in the system detected
it. It was found by looking, not by an alert.

**Evidence.** `results/SUMMARY_PLUGIN_VERIFICATION.md` documents the incident: `/health` answered
`laya-multilingual-coreml` with a `choice` calibration when it was supposed to serve the sentiment
model.

**Consequence.** A model registry in `config.yaml`, interchangeable adapters, and **hash verification
at startup**: if the real sha256 of the weights does not match the expected one, that model is not
loaded.

**Rejected alternative.** One service per model: it forces the client to know which one to call,
which is exactly the mistake being avoided.

## 2. Cardiff XLM-R as the default model

**Evidence** (240 texts, same thresholds, see `results/SUMMARY_BATTERY.md`):

| Model | Accuracy | Local accuracy | Median latency |
|---|---|---|---|
| Cardiff XLM-R | **91.67%** | **95.28%** | **10 ms** |
| Laya sentiment v1 (fine-tune) | 84.58% | 89.35% | 55 ms |
| Laya sentiment v2 (4.8x data) | 83.75% | 85.17% | 19 ms |

And on the sarcasm case, which is where it matters for a hybrid pattern: Cardiff gets it wrong at
0.68 confidence and **delegates**; v1 got it wrong at 0.91 and answered locally.

**The uncomfortable part, said up front**: this project's fine-tune loses to a model you can download
in two lines. The consequence is in `docs/PLAN.md`: what is presented here is the pattern and its
measurement, not a winning model.

## 3. A missing model does not prevent startup

**Why.** The full registry points at models that live on the author's machine. Validation raised an
exception when a path did not exist: **the service would not start on any other machine**.

**Evidence.** Verified with a config pointing at a nonexistent path: it loads, marks the model as
`available: false` and carries on. If someone routes to that model, the answer says so
(`model_unavailable`) instead of failing silently.

## 4. Routing by primitive, in a single service

**Why.** Sentiment (`noul`) and general decision (`choice`/`score`) are served by different models,
and the client should not have to know that.

**Evidence.** A single HTTP call answered by two models, with `model_used` on every answer;
`results/SUMMARY_GENERAL_ENGINE.md`.

**What was measured along the way, unexpectedly**: **the formulation matters more than the model**.
The same general engine scores 87.5% when sentiment is asked as `choice` and 53.3% as `noul` (in the
`noul` formulation it answers "no" to clearly positive texts).

## 5. The delegation policy, on calibrated confidence and per primitive

**Evidence** (1,740 texts, `results/SUMMARY_HARNESS_TEST.md`):

| | Cases | Model error |
|---|---|---|
| Delegated | 228 (13.1%) | **36.8%** |
| Not delegated | 1,512 (86.9%) | **6.3%** |

**5.86x more error on what is delegated**: the gate discriminates. And delegating genuinely helps:
labelling 38 delegated cases blind, the local model scores 63.2% and the LLM 84.2%, which takes
end-to-end accuracy from 89.71% to **92.47%**.

**Why the 0.75 threshold was not changed.** The measured curve says 0.90 would give more accuracy
(97.2% under the optimistic bound) at the cost of 15 more points of coverage. Choosing that point
depends on the relative cost of a cloud call versus an error, which is an operations decision, not a
technical one. It stays measured and configurable.

## 6. Neutral-mass threshold at 0.70

**The problem.** A neutral text ("The order arrived on Tuesday.") came back positive at 0.768 and
**did not delegate**: the binary reduction of a 3-class model cannot say "neutral".

**Evidence** (600 real neutral texts from class 1 of the original dataset, against the 1,740
non-neutral ones):

- Median `P(neutral)`: **0.528** on neutrals against **0.153** on non-neutrals. **AUC 0.814**.
- Threshold 0.70: delegates **32.7%** of neutrals at a cost of **+3.9 points** of traffic on
  non-neutrals, and that extra traffic carries twice the average error. At 0.50 it detects 54.0% but
  costs three times the traffic (+12.1 points) for the same marginal error.

**A correction that is on the record.** I picked 0.50 first, reading the F1 curve. That was the wrong
frame: F1 treats a false positive and a false negative alike, but here a false positive costs money.
The marginal table —the correct frame— moves the choice to 0.70. And I claimed the extra traffic had
23.7% error (which would make delegating it free); that number belonged to another rule: with the
implemented threshold it is **19.1%**, i.e. about twice the 10.3% average, so that extra traffic is
worth delegating. The policy is justified by the neutrals, not by
benchmark accuracy.

## 7. Truncation: configurable, reported, and it forces delegation

**The incident.** A 2,489-character message whose real sentiment sat in its last sentence was
classified **positive at 0.908 confidence and not delegated**. Cause: `max_length=128` hardcoded in
the adapter, so the model read the first quarter of the text. And the service did not say so.

**Decision.** `max_length` per model (512 for Cardiff, which is what XLM-R supports), truncation is
reported (`truncated`, `input_tokens`, `max_length`) and it **forces delegation**, because a
confident answer over partial text is worthless.

**Evidence.** Going from 128 to 512 does not degrade anything: 91.67% before and after on the same
sample. And long texts now delegate with the explicit reason `input_truncated(541 tokens > 512)`.

## 8. Serializing inference

**The incident.** With **two** concurrent requests the service died. Root cause in the log:

```
failed assertion _status < MTLCommandBufferStatusCommitted in -[IOGPUMetalCommandBuffer ...]
```

MPS/Metal is not thread-safe and FastAPI serves synchronous endpoints from a thread pool.

**Decision.** A global lock (`STATE["infer_lock"]`) around every model call.

**Evidence.** Before: 2 concurrent → crash (launchd restarting). After: **16/16 completed, the agent
never restarted**, 542 ms wall time.

## 9. Truthful `calibrated`

**Why.** The old service reported `calibrated: true` when all it knew was that a calibration file
existed. There was no temperature for `noul`, so confidence travelled **raw and labelled as
calibrated**.

**Decision.** `calibrated` is true only if a temperature was applied; otherwise the answer carries a
`calibration_note` explaining why. Today Cardiff travels with `calibrated: false`, and that is correct.

## 10. One canonical answer shape, with adapters

**Why.** `laya` and `laya-coreml` —two packages from the same project— **do not share a question
schema**: the high-level one uses `{type, instructions, criteria}` and the low-level one
`{t, ins, crit}`. Mixing them broke `choice` with an `AttributeError` over `None`.

**Decision.** One adapter per runtime, one canonical answer shape, and schema translation inside the
adapter. `laya` also returns `usage` with truncation information that the service was discarding.

## 11. Logging cannot take down a decision

**Decision.** All log writing runs inside `try/except`, with its own error counter, and `/metrics`
reports it. A logging failure is an observability problem, not a service outage.

**Evidence.** 0 errors across every run; the counter is visible in `/metrics`.

## 12. The demo uses the `transformers` path

**Why.** The Laya adapters need niche packages and CoreML requires macOS with Apple Silicon. If the
demo depended on that, half of anyone trying it would fall over at the first step.

**Decision.** `make demo` uses `config.demo.yaml` with a single model (Cardiff) and works on any
operating system. The Laya adapters are the documented `make setup-full` variant.

## 13. Apache-2.0

**Why.** The initial intent was GPL-2.0 "to follow Laya's path". On verifying it, Laya —its GitHub
repository, the `laya`/`laya-coreml` packages and the base model— declares **Apache-2.0**, not GPL.
And the FSF considers **Apache-2.0 incompatible with GPL-2.0**, though compatible with GPL-3.0.

**Decision.** Apache-2.0: it is Laya's license and it is compatible with every dependency. The
verified detail is in `docs/LICENSES.md`.

## 14. Do not oversell the model

**Evidence.** This project's fine-tune scores 86.0% and the baseline on the same benchmark 89.7%
(p = 1.3e-05); given only our 900 examples, that baseline reaches 88.8%. On top of that, a zero-shot
engine beats the fine-tune at its own task (87.5% against 84.6%).

**Decision.** The README says this up front. What is presented is the **hybrid pattern and its
measurement**: the delegation curve, the 5.86x error rate on what is delegated, the +2.76 end to end
and the observability. That is what is not commonly measured, and it is what holds this repository up.

---

<details>
<summary><h2>🇪🇸 Versión en Español — Haz clic aquí para desplegar</h2></summary>

# Decisiones y su evidencia

Cada decisión de diseño de este harness, con el dato que la sostiene. Nada acá es una preferencia
estética: todas salieron de un incidente o de una medición.

## 1. El modelo es configuración, no código

**Por qué.** El harness desplegado estaba sirviendo **otro modelo** del que la documentación decía:
el puerto lo ocupaba una versión vieja con un fine-tune de otra tarea, y nada en el sistema lo
detectaba. Se descubrió mirando, no por una alerta.

**Evidencia.** `results/SUMMARY_PLUGIN_VERIFICATION.md` documenta el incidente: `/health` respondía
`laya-multilingual-coreml` con una calibración `choice` cuando debía servir el modelo de sentimiento.

**Consecuencia.** Registro de modelos en `config.yaml`, adaptadores intercambiables, y **hash
verificado al arrancar**: si el sha256 real de los pesos no coincide con el esperado, ese modelo no
se carga.

**Alternativa descartada.** Un servicio por modelo: obliga al cliente a saber cuál llamar, que es
justo el error que se quiere evitar.

## 2. Cardiff XLM-R como modelo por defecto

**Evidencia** (240 textos, mismos umbrales, ver `results/SUMMARY_BATTERY.md`):

| Modelo | Accuracy | Accuracy local | Latencia mediana |
|---|---|---|---|
| Cardiff XLM-R | **91,67 %** | **95,28 %** | **10 ms** |
| Laya sentiment v1 (fine-tune) | 84,58 % | 89,35 % | 55 ms |
| Laya sentiment v2 (4,8× datos) | 83,75 % | 85,17 % | 19 ms |

Y en el caso de sarcasmo, que es donde importa para un patrón híbrido: Cardiff se equivoca con 0,68
de confianza y **deriva**; v1 se equivocaba con 0,91 y respondía local.

**Lo incómodo, dicho arriba**: el fine-tune de este proyecto pierde contra un modelo que se descarga
con dos líneas. La consecuencia está en `docs/PLAN.md`: lo que se presenta es el patrón y su
medición, no un modelo ganador.

## 3. Un modelo ausente no impide arrancar

**Por qué.** El registro completo apunta a modelos que viven en la máquina del autor. La validación
levantaba una excepción si la ruta no existía: **el servicio no arrancaba en ninguna otra máquina**.

**Evidencia.** Verificado con una config que apunta a una ruta inexistente: carga, marca el modelo
como `available: false` y sigue. Si alguien enruta a ese modelo, la respuesta lo dice
(`model_unavailable`) en vez de fallar en silencio.

## 4. Enrutamiento por primitiva, en un solo servicio

**Por qué.** Sentimiento (`noul`) y decisión general (`choice`/`score`) los sirven modelos distintos,
y el cliente no debería saberlo.

**Evidencia.** Una sola llamada HTTP contestada por dos modelos, con `model_used` en cada respuesta;
`results/SUMMARY_GENERAL_ENGINE.md`.

**Lo que se midió de paso, y no se esperaba**: la **formulación pesa más que el modelo**. El mismo
motor general acierta 87,5 % preguntando el sentimiento como `choice` y 53,3 % como `noul` (en la
formulación `noul` responde "no" a textos claramente positivos).

## 5. La política de derivación, sobre confianza calibrada y por primitiva

**Evidencia** (1.740 textos, `results/SUMMARY_HARNESS_TEST.md`):

| | Casos | Error del modelo |
|---|---|---|
| Derivados | 228 (13,1 %) | **36,8 %** |
| No derivados | 1.512 (86,9 %) | **6,3 %** |

**5,86× más error en lo derivado**: la compuerta discrimina. Y derivar mejora de verdad: etiquetando
a ciegas 38 casos derivados, el modelo local acierta 63,2 % y el LLM 84,2 %, lo que lleva la
accuracy de punta a punta de 89,71 % a **92,47 %**.

**Por qué no se cambió el umbral de 0,75.** La curva medida dice que 0,90 daría más accuracy
(97,2 % con la cota optimista) a cambio de 15 puntos más de cobertura. Elegir ese punto depende del
costo relativo de una llamada al cloud contra un error, que es una decisión de operación, no
técnica. Queda medido y configurable.

## 6. Umbral de masa neutral en 0,70

**El problema.** Un texto neutro ("El pedido llegó el martes.") salía positivo con 0,768 y **no
derivaba**: la reducción binaria de un modelo de 3 clases no sabe decir "neutro".

**Evidencia** (600 neutros reales de la clase 1 del dataset original, contra los 1.740 no neutros):

- Mediana de `P(neutro)`: **0,528** en neutros contra **0,153** en no neutros. **AUC 0,814**.
- Umbral 0,70: deriva el **32,7 %** de los neutros a cambio de **+3,9 puntos** de tráfico en los no
  neutros, y ese tráfico extra tiene el doble de error que el promedio. Con 0,50 se detecta el 54,0 %
  pero cuesta tres veces más tráfico (+12,1 puntos) con el mismo error marginal.

**Una corrección que quedó registrada.** Elegí 0,50 primero, leyendo la curva de F1. Estaba mal
encuadrado: la F1 trata igual un falso positivo que uno negativo, pero acá un falso positivo cuesta
dinero. La tabla marginal —que es el encuadre correcto— mueve la elección a 0,70. Y afirmé que el
tráfico extra tenía 23,7 % de error (sería gratis derivarlo); ese número era de otra regla: con el
umbral implementado es **19,1 %**, o sea unos el doble del promedio de 10,3 %, así que ese tráfico
extra conviene derivarlo. La política se justifica por los neutros, no
por precisión en el benchmark.

## 7. Truncación: configurable, reportada y obliga a derivar

**El incidente.** Un mensaje de 2.489 caracteres cuyo sentimiento real estaba en la última frase se
clasificaba **positivo con 0,908 de confianza y sin derivar**. Causa: `max_length=128` hardcodeado
en el adaptador, así que el modelo leía el primer cuarto del texto. Y el servicio no avisaba.

**Decisión.** `max_length` por modelo (512 para Cardiff, que es lo que soporta XLM-R), la truncación
se reporta (`truncated`, `input_tokens`, `max_length`) y **fuerza la derivación**, porque una
respuesta segura sobre texto parcial no vale.

**Evidencia.** Subir de 128 a 512 no degrada: 91,67 % antes y después en la misma muestra. Y los
textos largos ahora derivan con la razón explícita `input_truncated(541 tokens > 512)`.

## 8. Serializar la inferencia

**El incidente.** Con **dos** peticiones simultáneas el servicio moría. Causa raíz en el log:

```
failed assertion _status < MTLCommandBufferStatusCommitted in -[IOGPUMetalCommandBuffer ...]
```

MPS/Metal no es thread-safe y FastAPI atiende los endpoints sincrónicos en un pool de hilos.

**Decisión.** Un candado global (`STATE["infer_lock"]`) alrededor de cada llamada al modelo.

**Evidencia.** Antes: 2 concurrentes → caída (launchd reiniciando). Después: **16/16 completadas, el
agente sin reiniciarse**, latencia de pared 542 ms.

## 9. `calibrated` veraz

**Por qué.** El servicio viejo reportaba `calibrated: true` cuando lo único que sabía era que existía
un archivo de calibración. Para `noul` no había temperatura, así que la confianza viajaba **cruda y
etiquetada como calibrada**.

**Decisión.** `calibrated` es verdadero sólo si se aplicó una temperatura; si no, la respuesta trae
`calibration_note` explicando por qué. Hoy Cardiff viaja con `calibrated: false` y eso es correcto.

## 10. Una forma canónica de respuesta, con adaptadores

**Por qué.** `laya` y `laya-coreml` —dos paquetes del mismo proyecto— **no comparten el esquema de
pregunta**: el de alto nivel usa `{type, instructions, criteria}` y el de bajo nivel `{t, ins, crit}`.
Mezclarlos rompía `choice` con un `AttributeError` sobre `None`.

**Decisión.** Un adaptador por runtime, una forma canónica de respuesta, y la traducción de esquema
en el adaptador. `laya` trae además `usage` con información de truncación que el servicio estaba
descartando.

## 11. El registro no puede tumbar una decisión

**Decisión.** Toda la escritura del log va en `try/except`, con su propio contador de errores, y
`/metrics` lo reporta. Un fallo al registrar es un problema de observabilidad, no una caída del
servicio.

**Evidencia.** 0 errores en todas las corridas; el contador es visible en `/metrics`.

## 12. El demo usa el camino `transformers`

**Por qué.** Los adaptadores de Laya necesitan paquetes de nicho y el CoreML requiere macOS con Apple
Silicon. Si el demo dependiera de eso, la mitad de quien lo quiera probar se cae en el primer paso.

**Decisión.** `make demo` usa `config.demo.yaml` con un solo modelo (Cardiff) y funciona en cualquier
sistema operativo. Los adaptadores de Laya son la variante `make setup-full`, documentada.

## 13. Apache-2.0

**Por qué.** La intención inicial fue GPL-2.0 «para seguir el camino de Laya». Al verificarlo, Laya
—su repositorio en GitHub, los paquetes `laya`/`laya-coreml` y el modelo base— declara **Apache-2.0**,
no GPL. Y la FSF considera **Apache-2.0 incompatible con GPL-2.0**, aunque sí compatible con GPL-3.0.

**Decisión.** Apache-2.0: es la licencia de Laya y es compatible con todas las dependencias. Detalle
verificado en `docs/LICENSES.md`.

## 14. No vender el modelo

**Evidencia.** El fine-tune del proyecto mide 86,0 % y el baseline del mismo benchmark 89,7 %
(p = 1,3·10⁻⁵); y dado sólo nuestros 900 ejemplos, ese baseline llega a 88,8 %. Además un motor
zero-shot supera al fine-tune en su propia tarea (87,5 % contra 84,6 %).

**Decisión.** El README dice esto arriba. Lo que se presenta es el **patrón híbrido y su medición**:
la curva de derivación, el 5,86× de error en lo derivado, el +2,76 de punta a punta y la
observabilidad. Eso es lo que no es común tener medido, y es lo que sostiene el repo.

</details>
