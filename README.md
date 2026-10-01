# Harness híbrido de decisión local

Un servicio de decisión que corre **local**, responde con una confianza honesta y **deriva al cloud
cuando no está seguro**. El modelo que sirve es configuración, no código.

```bash
make setup    # entorno virtual + dependencias (una vez)
make demo     # arranca el servicio, muestra los casos y las métricas, y lo apaga
```

Funciona en cualquier sistema operativo con el camino por defecto (`transformers`). Los adaptadores
de Laya/CoreML —el motor para el que se construyó— son la variante `make setup-full`, en macOS con
Apple Silicon.

**Qué es y qué no es.** Lo que sigue es el patrón híbrido y su medición, no un modelo ganador: en
esta tarea el modelo local pierde contra un baseline que se descarga con dos líneas (86,0 % contra
89,7 %), y hasta un motor zero-shot lo supera. Lo que sí está medido y no es común tenerlo es el
resto: la curva de derivación, que el modelo se equivoca **5,86× más** en lo que deriva, y que el
patrón completo gana **+2,76 puntos** enviando el 13 % del tráfico al cloud. Nada de eso se afirma
sin el script que lo reproduce.

Mapa de la documentación:

| Documento | Para qué |
|---|---|
| `docs/DEMO.md` | la demostración, con su salida real |
| `docs/ARQUITECTURA.md` | cómo está armado y por qué |
| `docs/DECISIONES.md` | cada decisión con su evidencia |
| `docs/OPERACION.md` | desplegarlo, observarlo, cambiarlo, troubleshooting |
| `docs/LICENCIAS.md` | terceros, verificado |
| `docs/PLAN.md` | el plan de trabajo por fases |
| `results/RESUMEN_*.md` | **la evidencia**: cada número con su método |

## El servicio en detalle

Servicio FastAPI que expone decisiones tipadas (`noul`, `choice`, `score`) sobre un modelo local,
con política de derivación al cloud. **El modelo servido es configuración, no código**: se cambia
`active` en `config.yaml` o la variable `LAYA_ACTIVE_MODEL`.

Reemplaza al servicio de V3/V5, que tenía el modelo cableado y una calibración ambigua.

## Por qué existe

Auditando el harness desplegado aparecieron tres problemas que este servicio corrige por diseño:

| Problema en V3/V5 | Qué hace este servicio |
|---|---|
| El modelo estaba en el código; el servicio de V3 quedó corriendo con el modelo del PoC mientras la documentación decía V5 | El adaptador y los pesos salen de `config.yaml`; `/health` reporta **hash de los pesos** y si coincide con el esperado |
| `calibrated: true` significaba "hay un archivo de calibración", aunque no se aplicara ninguna temperatura | `calibrated` es verdadero **solo si se aplicó una T**, y la respuesta incluye `temperature` y, si no se pudo, `calibration_note` |
| La política de derivación solo aplicaba a `choice`; `noul` (el sentimiento) nunca delegaba | La política aplica a **todas** las primitivas, con umbral por tipo y sobre la confianza calibrada |
| El servicio no marcaba lo que no sabía hacer | Cada modelo declara `supports`; una primitiva no soportada vuelve como `unsupported_by_model`, no inventada |

## Uso

```bash
.venv/bin/python -m uvicorn service.server:app --host 127.0.0.1 --port 8091
# o con el modelo que se quiera servir:
LAYA_ACTIVE_MODEL=cardiff-xlmr .venv/bin/python -m uvicorn service.server:app --port 8091
```

### Endpoints

| Endpoint | Devuelve |
|---|---|
| `GET /health` | modelo activo, adaptador, primitivas soportadas, hash de pesos + `match`, temperaturas **por primitiva**, umbrales por tipo, `smoke_ok` |
| `GET /models` | el registro completo y cuál está activo |
| `POST /decide` | el contrato de siempre (`{state, questions}`), más los campos de honestidad |
| `POST /selftest` | corre los casos declarados en la config y dice cuáles pasan |

Contrato de una respuesta `noul`:

```json
{"id": "sentiment", "type": "noul", "value": true,
 "confidence": 0.9812, "raw_confidence": 0.9723,
 "calibrated": true, "temperature": 0.9, "calibration_note": null,
 "probs": [0.0188, 0.9812], "threshold": 0.75,
 "delegate_to_cloud": false, "delegate_reason": null, "supported": true}
```

## Adaptadores

| Adaptador | Sirve | Requisitos |
|---|---|---|
| `coreml` | Paquetes CoreML de Laya (`model.mlpackage` + `weight.bin`), ANE/GPU | `laya-coreml` |
| `laya` | Checkpoints Laya en safetensors, sin CoreML (x86/Linux/CI) | `laya` + `torch` |
| `transformers` | Clasificadores de Hugging Face; para 3 clases se reduce a binario con `binary_reduction` | `torch` + `transformers` |

Ojo: `laya-coreml` y `laya` **no comparten el esquema de pregunta** (`type`/`instructions` contra
`t`/`ins`). El adaptador traduce; no se asume una forma común.

## Garantías de arranque

- Si el hash de los pesos no es el declarado en `expect_sha256`, **el servicio no arranca**. Es la
  defensa contra "estoy sirviendo otro modelo y nada lo dice".
- Corre el self-test de `smoke` al arrancar. Si falla, arranca igual pero `/health` lo reporta como
  `smoke_ok: false` y queda en el log: un modelo que acierta mal es un problema de calidad, no de
  identidad, y conviene poder depurarlo con el servicio en pie.

## Batería de evaluación

`scripts/battery.py` mide el **pipeline** (modelo + calibración + umbral), no solo el modelo, sobre
una muestra determinista de textos con etiqueta:

```bash
bash scripts/run_battery_all.sh          # los tres modelos, cambiando solo LAYA_ACTIVE_MODEL
```

Reporta accuracy, tasa de derivación, **accuracy del subconjunto que se responde localmente**
(lo que el usuario recibe sin cloud), confianza media y latencia.

## Enrutamiento: sentimiento + motor general

Cada primitiva puede servirse con un modelo distinto (`routing` en `config.yaml`):

```yaml
routing:
  noul: cardiff-xlmr      # sentimiento, el mejor medido
  choice: laya-base       # motor de decisión general, zero-shot
  score: laya-base
preload: [cardiff-xlmr, laya-base]   # el resto del registro se carga al primer uso
```

Una sola llamada puede llevar las tres primitivas y cada respuesta indica con qué modelo se
contestó (`model_used`). Para comparar modelos sin tocar la config, `POST /decide` acepta
`"model": "<id>"` y fija ese modelo para todas las preguntas.

**Hallazgo medido**: la formulación pesa más que el modelo. El mismo `laya-base`, en la misma tarea
de sentimiento y la misma muestra de 240 textos, acierta **87,5 %** si se pregunta como `choice`
(positivo/negativo) y **53,3 %** si se pregunta como `noul` — en la formulación `noul` responde
"no" a textos claramente positivos. Un motor zero-shot supera así al fine-tune del proyecto.
Detalle en `results/RESUMEN_MOTOR_GENERAL.md`.

**Ojo con la carga perezosa**: cargar un modelo tarda 2,7-7 s y el plugin de DSH corta a 2,5 s. Todo
modelo que sirva alguna primitiva debe estar en `preload`, o la primera pregunta fallará por timeout.

## Uso diario

Después de reiniciar la máquina **el servicio ya está corriendo**: launchd lo levanta al iniciar
sesión. La terminal donde antes arrancabas el servicio (la "terminal A") ya no hace falta.

```bash
# 1. (opcional) comprobar que el servicio está arriba y con qué modelo
curl -s http://127.0.0.1:8090/health | python3 -m json.tool

# 2. levantar la interfaz de DSH con la tool de Laya registrada
cd ~/Projects/ml/Hybrid_Harness_V7 && bash scripts/start-dsh.sh
```

Si algo no responde:

```bash
launchctl print gui/$(id -u)/com.cesarmg.laya-decide | grep -E 'state|pid|runs'
launchctl kickstart -k gui/$(id -u)/com.cesarmg.laya-decide   # reiniciarlo a la fuerza
tail -50 ~/Projects/ml/Hybrid_Harness_V7/logs/launchd.err.log
```

> **Si direnv avisa `... .envrc is blocked`, corré `direnv allow` en este directorio.** El
> `.envrc` sólo fija `LAYA_SERVICE_URL` y el timeout; el plugin trae los mismos valores por
> defecto (8090 y 2500 ms), así que el aviso no rompe nada — pero conviene aprobarlo para que el
> entorno quede explícito. Las demás variables del `.envrc` son convenciones de V3 que este
> servicio no lee.

> **No corras más `Hybrid_Harness_V3/scripts/start-laya-service.sh`.** Ese era el servicio viejo
> (modelo del PoC, calibración `choice`). Ahora el puerto 8090 lo ocupa V7: ese script fallaría por
> puerto ocupado, y si llegara a arrancar, dejaría la tool respondiendo con el modelo equivocado.

## Arranque y persistencia

El servicio corre como **LaunchAgent** de launchd: arranca al iniciar sesión y se reinicia solo si
se cae.

```bash
scripts/install-launchd.sh                 # instala y arranca (modelo `active` de config.yaml)
LAYA_ACTIVE_MODEL=laya-sentiment-v1 scripts/install-launchd.sh   # o fijando el modelo
scripts/uninstall-launchd.sh               # lo descarga y detiene el servicio
launchctl print gui/$(id -u)/com.cesarmg.laya-decide | grep -E 'state|pid|runs'
tail -f logs/launchd.err.log
```

**Agente, no daemon.** Un LaunchAgent arranca cuando **el usuario inicia sesión**; no antes. Para
que arranque en el boot sin login haría falta un LaunchDaemon (como root), que además tendría que
poder leer la caché de modelos del usuario. Para una máquina personal el agente es lo correcto.

Política de reinicio: `KeepAlive` con `SuccessfulExit: false` y `ThrottleInterval: 30`. Si el
proceso muere (incluso con `kill -9`) launchd lo levanta; si el servicio **se niega a arrancar**
—por ejemplo porque el hash de los pesos no coincide— reintenta como mucho cada 30 segundos en vez
de entrar en un bucle cerrado.

> Si `launchctl bootstrap` devuelve `Bootstrap failed: 5: Input/output error`, casi siempre es el
> entorno desde el que se ejecuta, no el plist: desde un shell con sandbox restrictivo falla y desde
> una terminal normal funciona. `plutil -lint` sobre el plist lo confirma en un segundo.

`scripts/service-run.sh` es el punto de entrada que usa launchd (primer plano, sin `tee`); los logs
van a `logs/launchd.out.log` y `logs/launchd.err.log`.

## Resultados medidos

- `results/RESUMEN_BATERIA.md` — los tres modelos con la misma batería de 240 textos, con
  intervalos de Wilson y McNemar pareado.
- `results/RESUMEN_VERIFICACION_PLUGIN.md` — los dos plugins reales de DSH llamados contra este
  servicio, con los mismos 4 casos sobre v1 y sobre Cardiff.

## Estructura

```
config.yaml              registro de modelos, umbrales y casos de self-test
service/config.py        carga y valida el registro
service/backends.py      los tres adaptadores
service/calibration.py   temperatura por primitiva, aplicada y reportada con honestidad
service/schemas.py       contrato HTTP (compatible con el plugin de DSH)
service/server.py        FastAPI + arranque verificado + self-test
scripts/                 test de adaptadores, batería y comparación
```

## Concurrencia: leer antes de tocar el servicio

**MPS/Metal no es thread-safe.** FastAPI atiende los endpoints sincrónicos en un pool de hilos, así
que sin serializar, **dos peticiones simultáneas abortan el proceso**:

```
failed assertion _status < MTLCommandBufferStatusCommitted in -[IOGPUMetalCommandBuffer ...]
```

El servicio toma `STATE["infer_lock"]` alrededor de cada llamada al modelo (en `/decide` y en el
self-test). Verificado hasta 16 concurrentes: 16/16 completadas y el agente sin reiniciarse. Si
algunas vez se agrega un adaptador nuevo, **la llamada al modelo va dentro del candado**.

## Textos largos

`max_length` es configurable por modelo (Cardiff: 512 tokens). Cuando el texto no entra, la respuesta
lo dice (`truncated`, `input_tokens`, `max_length`) y **se deriva igual**, porque una respuesta
segura sobre texto parcial no vale. El umbral no salva de esto: un texto truncado puede dar 0,9 de
confianza.

## Política de derivación

El umbral vive en `config.yaml` (`delegation.per_type`) y aplica sobre la confianza calibrada. La
curva medida sobre 1.740 textos (Cardiff, umbral actual 0,75):

| Umbral | Cobertura local | Error local | Accuracy híbrida* |
|---|---|---|---|
| 0,75 | 86,9 % | 6,3 % | 94,5 % |
| 0,85 | 79,4 % | 4,3 % | 96,6 % |
| 0,90 | 71,8 % | 3,8 % | 97,2 % |

\* suponiendo que el cloud acierta todo lo derivado. Medido de verdad, con el LLM etiquetando a
ciegas 38 casos derivados: 92,5 % contra 89,7 % respondiendo todo local, con el 13 % del tráfico
derivado. Los detalles y los límites de esa medición están en
`results/RESUMEN_PRUEBA_HARNESS.md`.

## Observabilidad

Cada decisión queda registrada en `logs/decisions/decisions-<fecha>.jsonl` (un archivo por día,
rotación diaria, los más viejos se borran según `retain_days`).

Qué guarda cada registro: hora, largo y hash corto del texto, primitiva, **qué modelo contestó**,
valor, confianza cruda y calibrada, temperatura aplicada, masa neutral, si se truncó, si se derivó y
**por qué** (el motivo agrupado en su tipo: `high_neutral_mass`, `raw_confidence_below_0.75`,
`input_truncated`…), latencia y versión de calibración.

Nivel de detalle en `config.yaml`:

| `level` | Qué guarda del texto |
|---|---|
| `off` | nada |
| `metadata` | sólo números, hash y largo |
| **`excerpt`** (por defecto) | los primeros `excerpt_chars` caracteres |
| `full` | el texto completo (para depurar) |

**Garantía de diseño**: el registro va dentro de un `try/except` y nunca puede tumbar una decisión.
Medido en la primera tanda: 83 registros escritos, **0 errores**.

```bash
curl -s "http://127.0.0.1:8090/metrics?hours=24" | python3 -m json.tool   # métricas crudas
python scripts/report_decisions.py --hours 24                            # informe legible
python scripts/export_eval.py --hours 24 --out results/real_eval.jsonl   # exportar para etiquetar
```

`/metrics` informa: peticiones y respuestas, tasa de derivación global y **por primitiva**, mezcla de
modelos, motivos de derivación agrupados, latencias p50/p90/p95/p99, histogramas de confianza y de
**masa neutral**, largos, idiomas (heurística gruesa) y truncados.

El histograma de masa neutral es lo que permite recalibrar el umbral con la mezcla real de tráfico,
que es justamente lo que no se puede saber desde el test del dataset.

## Masa neutral

Cardiff es un clasificador de 3 clases; la reducción a binario descarta la masa neutral, así que un
texto sin sentimiento ("El pedido llegó el martes.") sale positivo con 0,768. La política ahora
también deriva cuando `P(neutro)` supera `delegation.neutral_mass_threshold` (0,70).

Medido sobre 600 neutros reales y los 1.740 no neutros: **AUC 0,81**; con 0,70 se deriva el 49 % de
los neutros a cambio de **+1,5 puntos** de tráfico en los no neutros. La tabla marginal completa y
por qué no se eligió 0,50 están en `results/RESUMEN_PRUEBA_HARNESS.md`.

El campo `neutral_mass` viaja en cada respuesta, y la razón de derivación lo dice:
`high_neutral_mass(0.809>0.7)`.

## Pendiente

- **Topics del repositorio**: se agregan desde la interfaz de GitHub; la API necesita token.
- **Batería con tráfico propio**: la herramienta existe (`scripts/export_eval.py` exporta las
  decisiones registradas para etiquetarlas y medir precisión real), falta acumular tráfico. El
  servicio ya lo registra desde el primer día.

Todo lo demás que estaba acá —observabilidad, el camino `choice`/`score` en los adaptadores de Laya—
está hecho y verificado: ver `docs/VERSIONADO.md`.
