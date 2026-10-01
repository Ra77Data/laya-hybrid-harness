# Versionado V7 — Servicio de decisión agnóstico del modelo

## Fecha: 2026-09-30

## Por qué existe

V7 no agrega un modelo: arregla el **despliegue**. Auditando el harness que estaba corriendo
aparecieron cuatro problemas que ninguna versión anterior detectaba:

| Problema encontrado | Qué hace V7 |
|---|---|
| El puerto 8090 lo ocupaba el servicio de **V3** (modelo del PoC, `587e4ac8…`), mientras la documentación decía que estaba desplegado V5 con el modelo validado | El modelo sale de `config.yaml`; `/health` reporta el **sha256 de los pesos** y si coincide con el esperado. Si no coincide, **no arranca** |
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

- Desplegado en `~/Projects/ml/Hybrid_Harness_V7/`, puerto 8090.
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
los 1.740 no neutros. AUC 0,81; con 0,70 se detecta el 49 % de los neutros por +1,5 puntos de
tráfico. Se descartó 0,50, que detecta más neutros pero cuesta cuatro veces más tráfico con el mismo
error local. Detalle en `results/SUMMARY_HARNESS_TEST.md`.

## Observabilidad

Cada decisión se registra en JSONL por día (`logs/decisions/`), con nivel de detalle configurable
(`off`/`metadata`/`excerpt`/`full`; por defecto `excerpt`: primeros 160 caracteres). Se guarda qué
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
