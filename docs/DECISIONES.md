# Decisiones y su evidencia

Cada decisión de diseño de este harness, con el dato que la sostiene. Nada acá es una preferencia
estética: todas salieron de un incidente o de una medición.

## 1. El modelo es configuración, no código

**Por qué.** El harness desplegado estaba sirviendo **otro modelo** del que la documentación decía:
el puerto lo ocupaba una versión vieja con un fine-tune de otra tarea, y nada en el sistema lo
detectaba. Se descubrió mirando, no por una alerta.

**Evidencia.** `results/RESUMEN_VERIFICACION_PLUGIN.md` documenta el incidente: `/health` respondía
`laya-multilingual-coreml` con una calibración `choice` cuando debía servir el modelo de sentimiento.

**Consecuencia.** Registro de modelos en `config.yaml`, adaptadores intercambiables, y **hash
verificado al arrancar**: si el sha256 real de los pesos no coincide con el esperado, ese modelo no
se carga.

**Alternativa descartada.** Un servicio por modelo: obliga al cliente a saber cuál llamar, que es
justo el error que se quiere evitar.

## 2. Cardiff XLM-R como modelo por defecto

**Evidencia** (240 textos, mismos umbrales, ver `results/RESUMEN_BATERIA.md`):

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
`results/RESUMEN_MOTOR_GENERAL.md`.

**Lo que se midió de paso, y no se esperaba**: la **formulación pesa más que el modelo**. El mismo
motor general acierta 87,5 % preguntando el sentimiento como `choice` y 53,3 % como `noul` (en la
formulación `noul` responde "no" a textos claramente positivos).

## 5. La política de derivación, sobre confianza calibrada y por primitiva

**Evidencia** (1.740 textos, `results/RESUMEN_PRUEBA_HARNESS.md`):

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
- Umbral 0,70: deriva el **48,7 %** de los neutros a cambio de **+1,5 puntos** de tráfico en los no
  neutros. Con 0,50 se detecta el 61,7 % pero cuesta cuatro veces más tráfico (+6,0 puntos).

**Una corrección que quedó registrada.** Elegí 0,50 primero, leyendo la curva de F1. Estaba mal
encuadrado: la F1 trata igual un falso positivo que uno negativo, pero acá un falso positivo cuesta
dinero. La tabla marginal —que es el encuadre correcto— mueve la elección a 0,70. Y afirmé que el
tráfico extra tenía 23,7 % de error (sería gratis derivarlo); ese número era de otra regla: con el
umbral implementado es **11,5 %**, o sea el promedio. La política se justifica por los neutros, no
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
verificado en `docs/LICENCIAS.md`.

## 14. No vender el modelo

**Evidencia.** El fine-tune del proyecto mide 86,0 % y el baseline del mismo benchmark 89,7 %
(p = 1,3·10⁻⁵); y dado sólo nuestros 900 ejemplos, ese baseline llega a 88,8 %. Además un motor
zero-shot supera al fine-tune en su propia tarea (87,5 % contra 84,6 %).

**Decisión.** El README dice esto arriba. Lo que se presenta es el **patrón híbrido y su medición**:
la curva de derivación, el 5,86× de error en lo derivado, el +2,76 de punta a punta y la
observabilidad. Eso es lo que no es común tener medido, y es lo que sostiene el repo.
