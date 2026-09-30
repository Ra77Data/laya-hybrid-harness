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
    "calibration_note": "sin temperatura para 'noul' (no hay archivo de calibración)",
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
| confianza calibrada < umbral por primitiva | el modelo duda | `results/RESUMEN_PRUEBA_HARNESS.md` |
| `P(neutro)` > `neutral_mass_threshold` | el texto no tiene sentimiento que clasificar | ídem |
| el texto no entró en la ventana del modelo | no vio todo el texto: su seguridad no vale | ídem |
| el modelo no soporta esa primitiva | no puede contestarla | — |

## Garantías de diseño

1. **El hash manda.** Si el sha256 real de los pesos no coincide con `expect_sha256`, ese modelo no
   se carga y el servicio lo dice. Nació de un incidente real: el servicio desplegado estaba
   sirviendo **otro modelo** del que la documentación decía.
2. **`calibrated` no miente.** Es verdadero sólo si se aplicó una temperatura a esa respuesta. Antes
   significaba "hay un archivo de calibración", que es otra cosa.
3. **Serialización de la inferencia.** MPS/Metal no es thread-safe: sin candado, **dos peticiones
   simultáneas abortaban el proceso**. Ver `docs/OPERACION.md`.
4. **El registro no puede tumbar una decisión.** Va en `try/except` y cuenta sus propios errores.
5. **Lo que no se sabe, se declara.** Primitiva no soportada, texto truncado, confianza cruda:
   todo viaja en la respuesta en vez de quedar implícito.

## Ver también

- `docs/DECISIONES.md` — cada decisión con la evidencia que la sostiene.
- `docs/OPERACION.md` — cómo se despliega, se observa y se cambia.
- `results/RESUMEN_*.md` — las mediciones, con su método.
