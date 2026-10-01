# End-to-end verification with the real DSH plugins

The payload was not reimplemented: each plugin's `.mjs` was imported in Node 22, the registered tool
was captured, and its `execute()` was called with the service pointed at by `LAYA_SERVICE_URL`.

Both plugins in the project were verified against the new service:

| Plugin | Registered tool | Parameters | Result |
|---|---|---|---|
| `Hybrid_Harness_V5/dsh-laya-plugin/` | `laya_sentiment` | `state`, `instructions` | 4/4 calls OK |
| `Hybrid_Harness_V3/dsh-laya-plugin/` | `laya_decide` | `state`, `questions` | 4/4 calls OK |

## Same 4 cases, two models served

| Case | `laya-sentiment-v1` (T=0.9) | `cardiff-xlmr` (no T) |
|---|---|---|
| clear positive | `true` 0.9812 → local | `true` 0.9845 → local |
| clear negative | `false` 0.9585 → local | `false` 0.9881 → local |
| ambiguous (contrast) | `false` 0.8753 → **local** | `true` 0.6409 → **DELEGATES** |
| sarcasm | `true` **0.9066** → local | `true` 0.6798 → **DELEGATES** |

Latency per call: 52-95 ms with v1, 12-227 ms with Cardiff (battery median: 10 ms). The plugin times
out at 1500 ms, so there is headroom; the service's startup self-test doubles as a warmup and avoids
paying for the first inference on the first real request.

## The two findings

1. **The case V5's documentation holds up as a delegation example no longer delegates.** With `T=0.9`
   (which *sharpens* the probabilities) the calibrated confidence rises to 0.8753 and sits above the
   0.75 threshold. Adjusting the temperature changed the gate's behaviour without anyone noticing.

2. **Sarcasm is the case that best explains what a gate is for.** Both models get it wrong (they say
   "positive"), but:
   - v1 gets it wrong **at 0.9066 confidence** and answers locally: the user receives a wrong and
     confident answer;
   - Cardiff gets it wrong **at 0.6798** and delegates to the cloud.

   In other words: the difference between the two models here is not accuracy but **knowing that they
   do not know**, which is exactly what the hybrid pattern needs. It is consistent with the error
   audit: sarcasm was the top category among high-confidence errors.

The delegation reason is explicit and honest: `raw_confidence_below_0.75(0.641);no_temperature_for_noul`
— it says the confidence is raw and that there is no temperature for that primitive, which is exactly
what used to be reported as `calibrated: true` without being so.

## Reproduce

```bash
LAYA_ACTIVE_MODEL=laya-sentiment-v1 .venv/bin/python -m uvicorn service.server:app --port 8091 &
LAYA_SERVICE_URL=http://127.0.0.1:8091 node scripts/check_plugin.mjs <path-to-the-plugin.mjs>
```

---

<details>
<summary><h2>🇪🇸 Versión en Español — Haz clic aquí para desplegar</h2></summary>

# Verificación end-to-end con los plugins reales de DSH

No se reimplementó el payload: se importó el `.mjs` de cada plugin en Node 22, se capturó la tool
registrada y se llamó a su `execute()` con el servicio apuntado por `LAYA_SERVICE_URL`.

Los dos plugins del proyecto quedaron verificados contra el servicio nuevo:

| Plugin | Tool registrada | Parámetros | Resultado |
|---|---|---|---|
| `Hybrid_Harness_V5/dsh-laya-plugin/` | `laya_sentiment` | `state`, `instructions` | 4/4 llamadas OK |
| `Hybrid_Harness_V3/dsh-laya-plugin/` | `laya_decide` | `state`, `questions` | 4/4 llamadas OK |

## Mismos 4 casos, dos modelos servidos

| Caso | `laya-sentiment-v1` (T=0,9) | `cardiff-xlmr` (sin T) |
|---|---|---|
| positivo claro | `true` 0,9812 → local | `true` 0,9845 → local |
| negativo claro | `false` 0,9585 → local | `false` 0,9881 → local |
| ambiguo (contraste) | `false` 0,8753 → **local** | `true` 0,6409 → **DERIVA** |
| sarcasmo | `true` **0,9066** → local | `true` 0,6798 → **DERIVA** |

Latencia por llamada: 52–95 ms con v1, 12–227 ms con Cardiff (mediana de la batería: 10 ms).
El plugin tiene un timeout de 1500 ms, así que hay margen; el self-test de arranque del servicio
sirve además de warmup y evita pagar la primera inferencia en la primera petición real.

## Los dos hallazgos

1. **El caso que la documentación de V5 exhibe como ejemplo de derivación ya no deriva.** Con
   `T=0,9` (que *afila* las probabilidades) la confianza calibrada sube a 0,8753 y queda por encima
   del umbral de 0,75. Ajustar la temperatura cambió el comportamiento de la compuerta sin que nadie
   lo notara.

2. **El sarcasmo es el caso que mejor explica para qué sirve una compuerta.** Los dos modelos se
   equivocan (dicen "positivo"), pero:
   - v1 se equivoca **con 0,9066 de confianza** y responde local: el usuario recibe una respuesta
     mal y segura;
   - Cardiff se equivoca **con 0,6798** y deriva al cloud.

   Es decir: la diferencia entre los dos modelos en este caso no es de accuracy sino de **saber que
   no saben**, que es exactamente lo que el patrón híbrido necesita. Y es coherente con la auditoría
   de errores: el sarcasmo era la primera categoría entre los errores de alta confianza.

La razón de derivación es explícita y honesta: `raw_confidence_below_0.75(0.641);no_temperature_for_noul`
   — dice que la confianza es cruda y que no hay temperatura para esa primitiva, que es justo lo que
   antes se reportaba como `calibrated: true` sin serlo.

## Reproducir

```bash
LAYA_ACTIVE_MODEL=laya-sentiment-v1 .venv/bin/python -m uvicorn service.server:app --port 8091 &
LAYA_SERVICE_URL=http://127.0.0.1:8091 node scripts/check_plugin.mjs <ruta-al-plugin.mjs>
```

</details>
