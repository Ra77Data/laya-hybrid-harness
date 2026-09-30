# Plan de acción — documentar y hacer demostrable el harness híbrido

## Estado

| Fase | Estado |
|---|---|
| 0 Decisiones | ✅ repo público, **Apache-2.0**, Cardiff en el demo, log en `excerpt`, plugin incluido |
| 1 Empaquetado | ✅ git, `pyproject` con extras, `Makefile`, `LICENSE`, `LICENCIAS.md`, `.env.example` |
| 2 Quickstart y demo | ✅ `make demo` + `docs/DEMO.md` con la salida real |
| 3 Verificación en limpio | 🔄 en curso — encontró un fallo real de instalación (ver abajo) |
| 4 Documentación | ✅ `ARQUITECTURA`, `DECISIONES`, `OPERACION` |
| 5 Publicación | ⏳ pendiente |
| 6 Presentación (opcional) | ⏳ pendiente |

### Lo que encontró la Fase 3

La prueba en limpio (`tests/quickstart_clean.sh`) falló en la primera corrida: el extra `[demo]` no
declaraba **`protobuf`**, que el extractor de tokenizers SentencePiece necesita. El error que da
transformers (`tiktoken is required to read a tiktoken file`) nombra a otro paquete y despista. En
el entorno del autor llegaba como dependencia transitiva de `coremltools`, así que **sólo se veía en
una instalación nueva**: exactamente el fallo que esta fase existe para encontrar.

Nota sobre la licencia: la decisión inicial fue GPL-2.0 «para seguir el camino de Laya», pero al
verificar resultó que **Laya es Apache-2.0** (su repo en GitHub y los paquetes `laya`/`laya-coreml`),
y la FSF considera Apache-2.0 incompatible con GPL-2.0. Se adoptó **Apache-2.0**.


Objetivo: que **otra persona pueda probar el harness en minutos**, entendiendo qué hace, qué no hace
y cómo se verifica, sin depender de tu máquina ni de tu árbol de proyecto.

## Punto de partida (lo que hay hoy)

| | Estado |
|---|---|
| Código del servicio | 8 módulos en `service/`, ~1.200 líneas, funcionando y desplegado |
| Scripts | 15 (sondas, baterías, informe, exportador, launchd) |
| Documentación | README + VERSIONADO + 4 resúmenes de resultados |
| **Distribución** | **no es un repo git**: nadie puede clonarlo, no hay historia ni tag |
| Empaquetado | sin `pyproject.toml`, sin `.env.example`, sin `LICENSE`, sin `.gitignore` |
| Tests | las sondas existen pero no hay un `make test` que las corra |
| Demo | no existe: el "demo" hoy es que yo llamo a la tool desde esta sesión |

**Diagnóstico**: el valor técnico está; lo que falta es todo lo que convierte un proyecto que
funciona en tu máquina en algo que otra persona puede ejecutar.

## Decisión de fondo: qué se puede demostrar de verdad

Hay tres capas y **no tienen la misma reproducibilidad**:

| Capa | Reproducible por un tercero | Por qué |
|---|---|---|
| **Servicio de decisión** (`/decide`, política, `/metrics`) | **Sí, en cualquier SO** | sólo necesita Python + `transformers` + el modelo Cardiff |
| Camino Laya/CoreML (ANE) | Sólo macOS Apple Silicon | necesita `laya`, `laya-coreml` y el paquete CoreML |
| Integración con DSH (la tool en el agente) | **No** | DSH no es público: se muestra como transcripción |

Consecuencia para el plan: **el demo por defecto usa el camino `transformers`** (funciona en Linux,
Windows y macOS Intel), y el camino Laya/CoreML es una variante "full" documentada. La integración
con DSH se presenta con una transcripción real, no como algo que el lector pueda correr.

## Fases

### Fase 0 — Decisiones (30 min, tuyas)

Nada de lo demás se puede cerrar sin esto:

1. **¿Repo público o privado?** y con qué licencia de código.
2. **¿Se publica `data/test_extended.jsonl`?** Es del benchmark UMSAB/TweetEval; hay que verificar
   su licencia antes (ver riesgo R2).
3. **Modelo por defecto del demo**: Cardiff (liviano, cualquier SO) o Laya v1 (la identidad del
   proyecto, pero sólo macOS).
4. **Nivel de log por defecto**: `excerpt` (160 caracteres) o `metadata` (sin texto).
5. **¿Se incluye el plugin de DSH en el repo?** (código sí, pero aclarando que necesita DSH).

### Fase 1 — Empaquetado mínimo (0,5-1 día)

- `git init`, `.gitignore` (venv, `logs/`, `.uvcache/`, `results/*.json` pesados), primer commit.
- `pyproject.toml` con dos extras: `[demo]` (transformers, torch, fastapi) y `[full]` (+ laya,
  laya-coreml).
- `.env.example` con las variables que importan (`LAYA_SERVICE_URL`, `LAYA_ACTIVE_MODEL`).
- `LICENSE` + `docs/LICENCIAS.md` con los modelos, datasets y paquetes de terceros.
- `Makefile` (o `justfile`) con: `setup`, `setup-full`, `serve`, `demo`, `test`, `metrics`, `report`.

**Criterio de aceptación**: `git clone` + `make setup` deja un entorno funcional sin leer nada más.

### Fase 2 — Quickstart y demo reproducible (1 día)

- **`make demo`**: un solo comando que crea el entorno si hace falta, arranca el servicio en un
  puerto libre, corre 8-10 casos elegidos, imprime la decisión de cada uno con su confianza, masa
  neutral y motivo de derivación, muestra `/metrics` y apaga el servicio.
- Los casos del demo tienen que **contar la historia**, no lucir el modelo:
  1. positivo claro → local
  2. negativo claro → local
  3. neutro factual → **deriva** por masa neutral
  4. sarcasmo → confianza media, decide la compuerta
  5. texto largo (2.500 caracteres) → **deriva** por truncación
  6. primitiva no soportada por el modelo de turno → **deriva** declarándolo
  7. vacío / sin contenido → **deriva**
  8. caso con enrutamiento: `choice` → lo contesta **otro modelo** (`laya-base`), si está disponible
- `docs/DEMO.md`: la transcripción esperada, con la salida real pegada y la explicación de cada
  caso. Sirve doble: guion para presentar y test de regresión (si la salida cambia, se ve).
- Camino sin Apple Silicon: `make demo` no debe requerir `laya-coreml` ni el paquete CoreML.

**Criterio de aceptación**: una persona sin el proyecto clonado ve el demo completo en < 10 minutos,
incluida la descarga del modelo.

### Fase 3 — Verificación de fricción (0,5 día) — **el gate más importante**

Reproducir el quickstart **en limpio**: directorio nuevo, sin venv, sin caché de modelos, sin el
árbol del proyecto, y midiendo el tiempo real hasta ver la salida del demo. Es la única forma de
saber si la fricción es la que creemos.

- Idealmente en otro usuario del sistema o en un contenedor Linux (prueba que el camino `transformers`
  es portable).
- Registrar cada tropiezo y corregirlo en el momento.
- **Si no corre en limpio, no está listo**: no se pasa a la Fase 5 sin esto.

### Fase 4 — Documentación (1-1,5 días)

Un punto de entrada y cuatro documentos de referencia, sin duplicar la evidencia que ya existe:

| Documento | Para qué |
|---|---|
| `README.md` | qué es, qué **no** es, quickstart de 3 comandos, resultados honestos, mapa de la documentación |
| `docs/ARQUITECTURA.md` | componentes, flujo, enrutamiento por primitiva, la política de derivación |
| `docs/DECISIONES.md` | las decisiones con su evidencia: por qué Cardiff, la curva del umbral, el umbral de masa neutral, por qué el candado de inferencia |
| `docs/OPERACION.md` | launchd, logs, `/metrics`, cambiar de modelo, troubleshooting, los dos fallos que encontramos |
| `docs/LICENCIAS.md` | terceros y qué implica para redistribuir |
| `results/RESUMEN_*.md` | **anexo de evidencia** (ya existen, se enlazan, no se reescriben) |

Regla: cada afirmación numérica del README tiene que apuntar al `RESUMEN_*.md` o al script que la
reproduce. Nada de números sin fuente.

### Fase 5 — Publicación (0,5 día)

- Repo con tag/release, `CITATION.cff` si va a citarse.
- Enlaces desde donde ya hay audiencia: la card del modelo en Hugging Face
  (`Ramg77/laya-sentiment-multilingual`), el informe y el paper.
- Un párrafo de "cómo lo pruebo en 5 minutos" en la card, que es el primer lugar donde alguien
  tropieza con esto.

### Fase 6 — (opcional) Pieza presentable (0,5 día)

- Guion de 5 minutos: qué se muestra, en qué orden, qué decir en cada caso.
- Una figura de arquitectura y una de la curva de derivación (la tabla ya está medida).
- Capturas o GIF del demo corriendo.

## Estimación

| Fase | Esfuerzo | Depende de |
|---|---|---|
| 0 Decisiones | 30 min tuyas | — |
| 1 Empaquetado | 0,5-1 día | Fase 0 |
| 2 Quickstart + demo | 1 día | Fase 1 |
| 3 Verificación en limpio | 0,5 día | Fase 2 |
| 4 Documentación | 1-1,5 días | Fases 2-3 |
| 5 Publicación | 0,5 día | Fase 3 |
| 6 Presentación (opcional) | 0,5 día | Fase 4 |

**Total: 4-5 días de trabajo efectivo.** El orden importa: el demo (Fase 2) antes que la
documentación (Fase 4), porque documentar algo que después cambia al probarlo en limpio es trabajo
tirado.

## Riesgos y trampas conocidas

- **R1 — Dependencias pesadas**: `torch` son ~2 GB y el modelo Cardiff 1,1 GB. El demo tiene que
  decir cuánto tarda y cuánto baja antes de empezar, no después.
- **R2 — Licencias de datos**: el benchmark (UMSAB/TweetEval) tiene licencia propia, y
  `tweet_sentiment_multilingual` suele ser **no comercial**. Hay que verificarlo antes de publicar
  `data/test_extended.jsonl` y antes de que alguien use esto en producción. Es un bloqueante de la
  Fase 5, no de las anteriores.
- **R3 — `laya`/`laya-coreml` son paquetes de nicho** y el CoreML sólo corre en Apple Silicon. Por
  eso el demo por defecto no los usa.
- **R4 — El log guarda texto de usuario**: el default `excerpt` mitiga, pero el `docs/OPERACION.md`
  tiene que decir explícitamente qué se guarda y cómo apagarlo.
- **R5 — DSH no es público**: la parte de "tool dentro del agente" no es reproducible por terceros.
  Se muestra como transcripción y se dice claro.
- **R6 — Sobreventa**: el modelo local pierde contra el baseline que se descarga con dos líneas
  (89,7 % contra 86,0 %), y en esta tarea un motor zero-shot supera al fine-tune del proyecto. El
  README tiene que decir esto arriba, no esconderlo al final: **lo que se presenta es el patrón
  híbrido y su medición, no un modelo ganador.**

## Qué NO entra en este plan

- Reentrenar o mejorar el modelo (fase cerrada).
- Publicar el paquete CoreML de nuevo (ya está publicado).
- Hacer el harness multi-tenant, con base de datos o desplegable en servidor: hoy es un servicio
  local para una persona, y el plan lo mantiene así.

## Primer corte recomendado

Si hay que elegir un camino corto para tener algo presentable cuanto antes:
**Fase 0 → Fase 1 → Fase 2 → Fase 3**, y recién después documentar. Con eso ya hay un repo clonable
y un `make demo` que corre en cualquier SO: eso es lo que permite que alguien lo pruebe.
