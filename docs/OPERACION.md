# Operación

## Instalación

```bash
make setup        # entorno + camino del demo (transformers). Cualquier sistema operativo.
make setup-full   # + adaptadores de Laya y CoreML (macOS con Apple Silicon)
```

El `Makefile` usa `uv` si está disponible y si no cae a `python -m venv`. Extras declarados en
`pyproject.toml`: `[demo]` y `[full]`.

## Arranque

```bash
make serve                       # primer plano, registro completo (config.yaml)
LAYA_ACTIVE_MODEL=laya-base make serve
LAYA_PORT=9000 make serve        # otro puerto, sin tocar la config
```

Variables que importan (ver `.env.example`):

| Variable | Para qué |
|---|---|
| `LAYA_CONFIG` | ruta a otro registro de modelos |
| `LAYA_ACTIVE_MODEL` | qué modelo sirve por defecto |
| `LAYA_PORT` | pisa el puerto de la config |
| `HF_HUB_CACHE` | dónde viven los modelos descargados |

### Como servicio persistente (macOS)

```bash
scripts/install-launchd.sh       # arranca al iniciar sesión y se reinicia si se cae
scripts/uninstall-launchd.sh
launchctl print gui/$(id -u)/com.cesarmg.laya-decide | grep -E 'state|pid|runs'
```

`KeepAlive` con `SuccessfulExit: false` y `ThrottleInterval: 30`: si el proceso muere, launchd lo
levanta; si el servicio **se niega a arrancar** (por ejemplo por un hash que no coincide), reintenta
como mucho cada 30 segundos en vez de entrar en un bucle.

Un LaunchAgent arranca **al iniciar sesión**, no antes. Para arrancar en el boot sin login haría
falta un LaunchDaemon como root, que además tendría que poder leer la caché de modelos del usuario.

## Observarlo

```bash
make smoke                        # ¿responde? ¿con qué modelo?
make metrics                      # métricas crudas de las últimas 24 h
make report                       # informe legible
curl -s localhost:8090/health | python3 -m json.tool
```

`/health` reporta: modelo activo, adaptador, primitivas soportadas, **sha256 real de los pesos y si
coincide con el esperado**, **qué primitivas tienen temperatura**, los umbrales de derivación, el
estado de cada modelo del registro (`loaded`, `smoke_ok`, `error`) y el self-test de arranque.

`/metrics?hours=N` agrega el tráfico registrado: derivación global y por primitiva, motivos agrupados
por tipo, mezcla de modelos, latencias p50/p90/p95/p99, histogramas de confianza y de masa neutral.

## Cambiar cosas

| Quiero cambiar | Se toca | Se aplica |
|---|---|---|
| el modelo que sirve una primitiva | `routing` en `config.yaml` | reiniciar el servicio |
| el umbral de confianza | `delegation.per_type` | reiniciar el servicio |
| el umbral de masa neutral | `delegation.neutral_mass_threshold` | reiniciar el servicio |
| qué modelos se precargan | `preload` | reiniciar el servicio |
| cuánto texto se guarda en el registro | `observability.level` | reiniciar el servicio |
| agregar un modelo | una entrada en `models:` | reiniciar el servicio |

Con launchd: `launchctl kickstart -k gui/$(id -u)/com.cesarmg.laya-decide`.

**Todo cambio de política se mide antes de fijarlo.** Las curvas de derivación y de masa neutral
están en `results/RESUMEN_PRUEBA_HARNESS.md`, y `scripts/neutral_gate.py` recalcula la segunda con
tráfico propio.

## Registro y privacidad

Cada decisión va a `logs/decisions/decisions-<fecha>.jsonl`, con rotación diaria y borrado de los
archivos más viejos que `retain_days` al arrancar.

| `observability.level` | Qué guarda del texto |
|---|---|
| `off` | nada |
| `metadata` | sólo números, hash y largo |
| `excerpt` (por defecto) | los primeros `excerpt_chars` caracteres |
| `full` | el texto completo |

Por defecto **no** se guarda el texto completo. Si el servicio va a procesar datos de terceros,
`metadata` es el nivel adecuado.

Para medir precisión sobre tráfico propio:

```bash
python scripts/export_eval.py --hours 24 --out results/real_eval.jsonl
# completar el campo 'target' (1 positivo / 0 negativo) y medir
```

## Cuando algo falla

| Síntoma | Causa más probable | Qué hacer |
|---|---|---|
| `laya_service_unavailable` en el cliente | el servicio no está arriba, o todavía carga modelos | `make smoke`; esperar ~15 s tras un reinicio |
| el servicio muere con varias peticiones a la vez | alguien sacó el candado de inferencia de `server.py` | ver "MPS no es thread-safe" abajo |
| respuestas seguras y equivocadas en textos largos | `max_length` muy chico, o la política de truncación desactivada | revisar `max_length` y que `truncated` fuerce derivación |
| un texto neutro sale positivo con 0,77 | el umbral de masa neutral está en `null` | fijarlo (0,70 medido; ver `RESUMEN_PRUEBA_HARNESS.md`) |
| `calibrated: false` en todo | el modelo de turno no tiene temperatura ajustada | es correcto: la confianza es cruda y se declara |
| el servicio no arranca tras cambiar un modelo | el hash no coincide con `expect_sha256` | corregir la entrada; es la garantía funcionando |
| en un entorno nuevo: `tiktoken is required to read a tiktoken file` | falta `protobuf`, que el extractor de SentencePiece necesita (el mensaje nombra a tiktoken y confunde) | `pip install protobuf`; ya está en el extra `[demo]` |
| direnv: `.envrc is blocked` | falta aprobar el archivo | `direnv allow` en el directorio |
| `launchctl bootstrap: 5: Input/output error` | permisos del shell, no del plist | probar desde una terminal normal; `plutil -lint` para descartar el plist |

### MPS no es thread-safe (leer antes de tocar `server.py`)

FastAPI atiende los endpoints sincrónicos en un pool de hilos. Sin serializar, **dos peticiones
simultáneas abortan el proceso** con una aserción de Metal:

```
failed assertion _status < MTLCommandBufferStatusCommitted in -[IOGPUMetalCommandBuffer ...]
```

El servicio toma `STATE["infer_lock"]` alrededor de cada llamada al modelo, en `/decide` y en el
self-test. Verificado hasta 16 concurrentes: 16/16 completadas y el agente sin reiniciarse. **Si se
agrega un adaptador nuevo, la llamada al modelo va dentro del candado.**

## Verificación

```bash
make test                        # self-test + casos límite + concurrencia
bash tests/quickstart_clean.sh   # el quickstart completo, en un directorio limpio
make demo                        # la demostración, con la salida esperada en docs/DEMO.md
```
