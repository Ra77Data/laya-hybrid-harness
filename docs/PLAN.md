# Action plan — documenting and making the hybrid harness demonstrable

## Status

| Phase | Status |
|---|---|
| 0 Decisions | ✅ public repo, **Apache-2.0**, Cardiff in the demo, `excerpt` logging, plugin included |
| 1 Packaging | ✅ git, `pyproject` with extras, `Makefile`, `LICENSE`, `docs/LICENSES.md`, `.env.example` |
| 2 Quickstart and demo | ✅ `make demo` + `docs/DEMO.md` with the real output |
| 3 Clean verification | ✅ passes end to end (see below); it found **two real failures** |
| 4 Documentation | ✅ ARCHITECTURE, DECISIONS, OPERATIONS, LICENSES, DEMO, PLAN, VERSIONING |
| 5 Publication | ✅ public repo, tag `v1.0.0`, Release with notes and 10 topics |
| 6 Presentation (optional) | ⏳ not done (5-minute script and figures) |

### What Phase 3 found

The clean test (`tests/quickstart_clean.sh`) found **two failures that only appear in a fresh
install** — which is exactly what this phase exists for:

1. **`protobuf` was not declared in the `[demo]` extra.** The SentencePiece tokenizer extractor needs
   it, and the error transformers raises (`tiktoken is required to read a tiktoken file`) names a
   different package and misleads. In the author's environment it arrived as a transitive dependency
   of `coremltools`, so it never showed up.
2. **The self-test marked models as failed when their adapter was not installed.** In a `[demo]`
   environment the four Laya models fail with `ModuleNotFoundError`, and `make test` reported
   `passed: false`. That is not a model failure: it means `make setup-full` is missing. Three things
   now have to be distinguished —the weights exist, the adapter is installed, the model is
   servable— and skipped models are reported with an actionable reason.

Numbers from the clean run, with **empty** uv and model caches:

| Step | Time | What it implies |
|---|---|---|
| `git clone` | 0 s | 61 files; no venv or log travels in the repo |
| `make setup` | 75 s | 766 MB environment |
| `make demo` | 148 s | includes the 1.1 GB model download |
| `make test` | 25 s | self-test + 19 edge cases + concurrency |

**From zero to a working demo: ~4 minutes.** The test is in `tests/quickstart_clean.sh` so anyone can
repeat it.

A note on the license: the initial decision was GPL-2.0 "to follow Laya's path", but on verifying it
**Laya turned out to be Apache-2.0** (its GitHub repo and the `laya`/`laya-coreml` packages), and the
FSF considers Apache-2.0 incompatible with GPL-2.0. **Apache-2.0** was adopted.

## Goal

That **another person can try the harness in minutes**, understanding what it does, what it does not
do and how it is verified, without depending on your machine or your project tree.

## Starting point (what existed then)

| | State |
|---|---|
| Service code | 8 modules under `service/`, ~1,200 lines, working and deployed |
| Scripts | 15 (probes, batteries, report, exporter, launchd) |
| Documentation | README + VERSIONING + 4 result summaries |
| **Distribution** | **not a git repo**: nobody could clone it, no history, no tag |
| Packaging | no `pyproject.toml`, no `.env.example`, no `LICENSE`, no `.gitignore` |
| Tests | the probes existed but there was no `make test` to run them |
| Demo | did not exist: the "demo" was me calling the tool from this session |

**Diagnosis**: the technical value was there; what was missing is everything that turns a project that
works on your machine into something another person can run.

## The underlying decision: what can genuinely be demonstrated

There are three layers and **they are not equally reproducible**:

| Layer | Reproducible by a third party | Why |
|---|---|---|
| **Decision service** (`/decide`, policy, `/metrics`) | **Yes, on any OS** | it only needs Python + `transformers` + the Cardiff model |
| Laya/CoreML path (ANE) | macOS Apple Silicon only | it needs `laya`, `laya-coreml` and the CoreML package |
| DSH integration (the tool inside the agent) | **No** | DSH is not public: shown as a transcript |

Consequence for the plan: **the default demo uses the `transformers` path** (works on Linux, Windows
and macOS Intel), and the Laya/CoreML path is a documented "full" variant. The DSH integration is
presented as a real transcript, not as something the reader can run.

## Phases

### Phase 0 — Decisions (30 min, yours)

Nothing else can be closed without this:

1. **Public or private repo?** And under which code license.
2. **Is `data/test_extended.jsonl` published?** It comes from the UMSAB/TweetEval benchmark; its
   license has to be checked first (see risk R2).
3. **Default demo model**: Cardiff (light, any OS) or Laya v1 (the project's identity, but macOS only).
4. **Default log level**: `excerpt` (160 characters) or `metadata` (no text).
5. **Is the DSH plugin included in the repo?** (the code yes, stating that it needs DSH).

### Phase 1 — Minimal packaging (0.5-1 day)

- `git init`, `.gitignore` (venv, `logs/`, `.uvcache/`, heavy `results/*.json`), first commit.
- `pyproject.toml` with two extras: `[demo]` (transformers, torch, fastapi) and `[full]` (+ laya,
  laya-coreml).
- `.env.example` with the variables that matter (`LAYA_SERVICE_URL`, `LAYA_ACTIVE_MODEL`).
- `LICENSE` + `docs/LICENSES.md` covering third-party models, datasets and packages.
- `Makefile` with: `setup`, `setup-full`, `serve`, `demo`, `test`, `metrics`, `report`.

**Acceptance criterion**: `git clone` + `make setup` leaves a working environment without reading
anything else.

### Phase 2 — Quickstart and reproducible demo (1 day)

- **`make demo`**: a single command that creates the environment if needed, starts the service on a
  free port, runs 8-10 chosen cases, prints each decision with its confidence, neutral mass and
  delegation reason, shows `/metrics` and shuts the service down.
- The demo cases have to **tell a story**, not show off the model:
  1. clear positive → local
  2. clear negative → local
  3. factual neutral → **delegates** on neutral mass
  4. sarcasm → medium confidence, the gate decides
  5. long text (2,500 characters) → **delegates** on truncation
  6. primitive unsupported by the model in turn → **delegates** declaring it
  7. empty / no content → **delegates**
  8. a routing case: `choice` → answered by **another model** (`laya-base`), when available
- `docs/DEMO.md`: the expected transcript, with the real output pasted in and an explanation of each
  case. It serves twice: as a script for presenting and as a regression test (if the output changes,
  it shows).
- Path without Apple Silicon: `make demo` must not require `laya-coreml` or the CoreML package.

**Acceptance criterion**: someone who has not cloned the project sees the full demo in under 10
minutes, including the model download.

### Phase 3 — Friction verification (0.5 day) — **the most important gate**

Reproduce the quickstart **from clean**: new directory, no venv, no model cache, none of the project
tree, and measure the real time until the demo output appears. It is the only way to know whether the
friction is what we think it is.

- Ideally as another system user or in a Linux container (proving the `transformers` path is
  portable).
- Record every stumble and fix it on the spot.
- **If it does not run clean, it is not ready**: Phase 5 does not start without this.

### Phase 4 — Documentation (1-1.5 days)

One entry point and a set of reference documents, without duplicating evidence that already exists:

| Document | Purpose |
|---|---|
| `README.md` | what it is, what it is **not**, a 3-command quickstart, honest results, documentation map |
| `docs/ARCHITECTURE.md` | components, flow, routing by primitive, the delegation policy |
| `docs/DECISIONS.md` | the decisions with their evidence: why Cardiff, the threshold curve, the neutral-mass threshold, why the inference lock |
| `docs/OPERATIONS.md` | launchd, logs, `/metrics`, changing models, troubleshooting, the two failures we found |
| `docs/LICENSES.md` | third parties and what it implies for redistribution |
| `results/SUMMARY_*.md` | **evidence annex** (they already exist, they are linked, not rewritten) |

Rule: every numeric claim in the README has to point at a `SUMMARY_*.md` or at the script that
reproduces it. No numbers without a source.

### Phase 5 — Publication (0.5 day)

**One concrete step was needed before publishing.** The `config.yaml` that was versioned and the one
the deployment uses are **the same file**, and it holds several absolute paths from the author's
machine for the Laya models. Publishing it that way leaks the directory structure and helps nobody.
The step was: version a `config.example.yaml` with documented placeholders, take `config.yaml` out of
version control, and adjust the deployment sync so it keeps its own real one. `config.demo.yaml` (the
one `make demo` uses) has no absolute paths and was publishable as it stood.

The rest of the phase is mechanical: create the remote, `git remote add`, push, tag and links from
the model card on Hugging Face.

- Repo with tag/release, `CITATION.cff` if it is going to be cited.
- Links from where there is already an audience: the model card on Hugging Face
  (`Ramg77/laya-sentiment-multilingual`), the report and the paper.
- A "how do I try this in 5 minutes" paragraph on the card, which is the first place someone stumbles
  into this.

### Phase 6 — (optional) Presentable piece (0.5 day)

- A 5-minute script: what is shown, in what order, what to say about each case.
- One architecture figure and one delegation-curve figure (the table is already measured).
- Screenshots or a GIF of the demo running.

## Estimate

| Phase | Effort | Depends on |
|---|---|---|
| 0 Decisions | 30 min of yours | — |
| 1 Packaging | 0.5-1 day | Phase 0 |
| 2 Quickstart + demo | 1 day | Phase 1 |
| 3 Clean verification | 0.5 day | Phase 2 |
| 4 Documentation | 1-1.5 days | Phases 2-3 |
| 5 Publication | 0.5 day | Phase 3 |
| 6 Presentation (optional) | 0.5 day | Phase 4 |

**Total: 4-5 days of effective work.** Order matters: the demo (Phase 2) before the documentation
(Phase 4), because documenting something that then changes when tested clean is wasted work.

## Risks and known traps

- **R1 — Heavy dependencies**: `torch` is ~2 GB and the Cardiff model 1.1 GB. The demo has to say how
  long it takes and how much it downloads before it starts, not after.
- **R2 — Data licenses**: the benchmark (UMSAB/TweetEval) has its own license, and
  `tweet_sentiment_multilingual` is often **non-commercial**. It has to be verified before publishing
  `data/test_extended.jsonl` and before anyone uses this in production. It blocked Phase 5, not the
  earlier phases.
- **R3 — `laya`/`laya-coreml` are niche packages** and CoreML only runs on Apple Silicon. That is why
  the default demo does not use them.
- **R4 — The log keeps user text**: the `excerpt` default mitigates it, but `docs/OPERATIONS.md` has
  to state explicitly what is kept and how to turn it off.
- **R5 — DSH is not public**: the "tool inside the agent" part is not reproducible by third parties.
  It is shown as a transcript and said clearly.
- **R6 — Overselling**: the local model loses to a baseline you download in two lines (89.7% against
  86.0%), and on this task a zero-shot engine beats the project's fine-tune. The README has to say
  this up front, not hide it at the end: **what is presented is the hybrid pattern and its
  measurement, not a winning model.**

## What this plan does NOT include

- Retraining or improving the model (a closed phase).
- Publishing the CoreML package again (it is already published).
- Making the harness multi-tenant, database-backed or server-deployable: today it is a local service
  for one person, and the plan keeps it that way.

## Recommended first cut

If a short path is needed to have something presentable as soon as possible:
**Phase 0 → Phase 1 → Phase 2 → Phase 3**, and only then document. That already gives a clonable repo
and a `make demo` that runs on any OS: that is what lets someone try it.

---

<details>
<summary><h2>🇪🇸 Versión en Español — Haz clic aquí para desplegar</h2></summary>

# Plan de acción — documentar y hacer demostrable el harness híbrido

## Estado

| Fase | Estado |
|---|---|
| 0 Decisiones | ✅ repo público, **Apache-2.0**, Cardiff en el demo, log en `excerpt`, plugin incluido |
| 1 Empaquetado | ✅ git, `pyproject` con extras, `Makefile`, `LICENSE`, `docs/LICENSES.md`, `.env.example` |
| 2 Quickstart y demo | ✅ `make demo` + `docs/DEMO.md` con la salida real |
| 3 Verificación en limpio | ✅ pasa de punta a punta (ver abajo); encontró **dos fallos reales** |
| 4 Documentación | ✅ ARCHITECTURE, DECISIONS, OPERATIONS, LICENSES, DEMO, PLAN, VERSIONING |
| 5 Publicación | ✅ repo público, tag `v1.0.0`, Release con notas y 10 topics |
| 6 Presentación (opcional) | ⏳ no hecha (guion de 5 minutos y figuras) |

### Lo que encontró la Fase 3

La prueba en limpio (`tests/quickstart_clean.sh`) encontró **dos fallos que sólo aparecen en una
instalación nueva** — que es exactamente para lo que existe esta fase:

1. **`protobuf` no estaba declarado en el extra `[demo]`.** El extractor de tokenizers SentencePiece
   lo necesita, y el error que da transformers (`tiktoken is required to read a tiktoken file`)
   nombra a otro paquete y despista. En el entorno del autor llegaba como dependencia transitiva de
   `coremltools`, así que nunca se notó.
2. **El self-test daba por fallados los modelos cuyo adaptador no está instalado.** En un entorno
   `[demo]` los cuatro modelos de Laya fallan con `ModuleNotFoundError`, y `make test` reportaba
   `passed: false`. No es un fallo del modelo: es que hace falta `make setup-full`. Ahora hay que
   distinguir **tres** cosas —los pesos existen, el adaptador está instalado, el modelo es
   servible— y los omitidos se reportan con la razón accionable.

Números de la corrida en limpio, con cachés de uv y de modelos **vacías**:

| Paso | Tiempo | Qué implica |
|---|---|---|
| `git clone` | 0 s | 61 archivos; ningún venv ni log viaja en el repo |
| `make setup` | 75 s | entorno de 766 MB |
| `make demo` | 148 s | incluye la descarga de 1,1 GB del modelo |
| `make test` | 25 s | self-test + 19 casos límite + concurrencia |

**De cero a demo funcionando: ~4 minutos.** La prueba quedó en `tests/quickstart_clean.sh` para que
cualquiera la repita.

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
| Documentación | README + VERSIONING + 4 resúmenes de resultados |
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
- `LICENSE` + `docs/LICENSES.md` con los modelos, datasets y paquetes de terceros.
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
| `docs/ARCHITECTURE.md` | componentes, flujo, enrutamiento por primitiva, la política de derivación |
| `docs/DECISIONS.md` | las decisiones con su evidencia: por qué Cardiff, la curva del umbral, el umbral de masa neutral, por qué el candado de inferencia |
| `docs/OPERATIONS.md` | launchd, logs, `/metrics`, cambiar de modelo, troubleshooting, los dos fallos que encontramos |
| `docs/LICENSES.md` | terceros y qué implica para redistribuir |
| `results/SUMMARY_*.md` | **anexo de evidencia** (ya existen, se enlazan, no se reescriben) |

Regla: cada afirmación numérica del README tiene que apuntar al `SUMMARY_*.md` o al script que la
reproduce. Nada de números sin fuente.

### Fase 5 — Publicación (0,5 día)

**Hizo falta un paso concreto antes de publicar.** El `config.yaml` que se versionaba y el que usa el
despliegue son **el mismo archivo**, y tiene varias rutas absolutas a la máquina del autor para los
modelos de Laya. Publicarlo así filtra la estructura de directorios y no le sirve a nadie. El paso
fue: versionar `config.example.yaml` con placeholders documentados, sacar `config.yaml` del control
de versiones, y ajustar la sincronización del despliegue para que conserve el suyo real.
`config.demo.yaml` (el del `make demo`) no tiene rutas absolutas y ya era publicable tal cual.

El resto de la fase es mecánico: crear el remoto, `git remote add`, push, tag y enlaces desde la
tarjeta del modelo en Hugging Face.

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
- **R4 — El log guarda texto de usuario**: el default `excerpt` mitiga, pero el `docs/OPERATIONS.md`
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

</details>
