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

3. La razón de derivación es explícita y honesta: `raw_confidence_below_0.75(0.641);no_temperature_for_noul`
   — dice que la confianza es cruda y que no hay temperatura para esa primitiva, que es justo lo que
   antes se reportaba como `calibrated: true` sin serlo.

## Reproducir

```bash
LAYA_ACTIVE_MODEL=laya-sentiment-v1 .venv/bin/python -m uvicorn service.server:app --port 8091 &
LAYA_SERVICE_URL=http://127.0.0.1:8091 node scripts/check_plugin.mjs <ruta-al-plugin.mjs>
```
