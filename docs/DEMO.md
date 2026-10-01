# Demo

One command, nothing else to clone, no Apple Silicon and no DSH:

```bash
make setup     # creates the virtual environment and installs (once; ~2 GB with torch)
make demo      # starts the service, shows the cases, prints the metrics and shuts it down
```

The first time, the Cardiff XLM-R model (~1.1 GB) is downloaded from the Hugging Face Hub. The demo
uses `config.demo.yaml`, a minimal registry with **a single model**: that is why the last case (a
primitive that model does not implement) shows what the harness does when it cannot do something.

## What each case demonstrates

| Case | What it shows |
|---|---|
| clear positive / negative | the normal path: answered **locally** with high confidence |
| sarcasm | the model **gets it wrong** (`value=True`) but at 0.68 confidence: the harness **delegates**. This is the hybrid pattern working: it does not get it right, but it knows it does not know |
| neutral ("The order arrived on Tuesday.") | `P(neutral)=0.81` crosses the 0.70 threshold: **delegates** instead of inventing a sentiment |
| empty input | confidence 0.53: **delegates** |
| long text (2,400 chars) | 536 tokens against a 512 window: **delegates**, because a confident answer over partial text is worthless |
| unsupported primitive | the model declares support for `noul` only; a `choice` question comes back as `unsupported_by_model` and **delegates**, instead of making up an answer |

Cases marked `[ok]` are asserted: if they change, the demo shows it. Sarcasm goes with `[·]` because
it is **not asserted**: the model may or may not get it right depending on the text, and what matters
is that when it is unsure, it delegates. Asserting it would make the demo depend on the confidence of
one specific case.

## Real output

This transcript is the output of `bash scripts/demo.sh`, copied verbatim (not retyped):

```text
=== starting the service on 8091 with config.demo.yaml
    the first time it downloads Cardiff XLM-R (~1.1 GB) from Hugging Face

model served: cardiff-xlmr (transformers) | routing: {'noul': 'cardiff-xlmr'}
confidence thresholds: {'noul': 0.75, 'choice': 0.75, 'score': 0.75} | neutral mass: 0.7

  [ok] clear positive                     local    value=True     conf=0.985 (raw) neutral=0.05 model=cardiff-xlmr
  [ok] clear negative                     local    value=False    conf=0.988 (raw) neutral=0.05 model=cardiff-xlmr
  [·] sarcasm                            DELEGATE value=True     conf=0.680 (raw) neutral=0.21 model=cardiff-xlmr
        reason: raw_confidence_below_0.75(0.680);no_temperature_for_noul
  [ok] neutral (high neutral mass)        DELEGATE value=True     conf=0.768 (raw) neutral=0.81 model=cardiff-xlmr
        reason: high_neutral_mass(0.809>0.7)
  [ok] no content                         DELEGATE value=False    conf=0.527 (raw) neutral=0.34 model=cardiff-xlmr
        reason: raw_confidence_below_0.75(0.527);no_temperature_for_noul
  [ok] long: the ending flips the meaning DELEGATE value=True     conf=0.622 (raw) neutral=0.51 model=cardiff-xlmr
        reason: input_truncated(536 tokens > 512);raw_confidence_below_0.75(0.622);no_temperature_for_noul
  [ok] primitive the model does not support DELEGATE value=None     conf=0.000 (raw) neutral=  -  model=cardiff-xlmr
        reason: unsupported_by_model(cardiff-xlmr)

=== what was logged (observability)
  requests 21 | answers 21 | delegated 15 (71.4 %)
  reasons: {'raw_confidence_below_0.75': 6, 'high_neutral_mass': 3, 'input_truncated': 3, 'unsupported_by_model': 3}
  models: {'cardiff-xlmr': 21}
  latency: p50 100.09 ms | p95 312.0 ms
  log at: logs/decisions (level excerpt, 7 written, 0 errors)

=== demo finished. To actually leave it running:  make serve
    (or 'bash scripts/demo.sh --keep' so it is not shut down at the end)
```

## What the demo does NOT show

- **The agent integration (DSH)**: the plugin lives in `dsh-laya-plugin/` and is verified against
  this same service, but DSH is not public, so that part is not reproducible by a third party. It is
  documented as an optional integration.
- **The Laya adapters** (`laya`, `laya-coreml`): they need local paths or heavier downloads, and the
  CoreML path requires macOS with Apple Silicon. `make setup-full` plus the full registry
  (`config.yaml`) enables them, including **routing by primitive**: `noul` to the sentiment model and
  `choice`/`score` to a general decision engine.
- **The model's accuracy**: the demo shows decisions, not quality. The measurements —including the
  comparison against the baseline that wins— are in `results/SUMMARY_*.md`.

## Automated verification

```bash
make test      # model self-test + edge cases + concurrency
make metrics   # metrics for the logged traffic
make report    # human-readable report
```

---

<details>
<summary><h2>🇪🇸 Versión en Español — Haz clic aquí para desplegar</h2></summary>

# Demostración

Un comando, sin clonar nada más, sin Apple Silicon y sin DSH:

```bash
make setup     # crea el entorno virtual e instala (una vez; ~2 GB con torch)
make demo      # arranca el servicio, muestra los casos, imprime las métricas y lo apaga
```

La primera vez, el modelo Cardiff XLM-R (~1,1 GB) se descarga del Hub de Hugging Face. El demo usa
`config.demo.yaml`, un registro mínimo con **un solo modelo**: por eso el caso del final (una
primitiva que ese modelo no implementa) muestra qué hace el harness cuando no sabe hacer algo.

## Qué demuestra cada caso

| Caso | Qué muestra |
|---|---|
| positivo / negativo claro | el camino normal: se responde **local** con confianza alta |
| sarcasmo | el modelo **se equivoca** (`value=True`) pero con 0,68 de confianza: el harness **deriva**. Es el patrón híbrido funcionando: no acierta, pero sabe que no sabe |
| neutro ("El pedido llegó el martes.") | `P(neutro)=0,81` supera el umbral 0,70: **deriva** en vez de inventar un sentimiento |
| sin contenido | confianza 0,53: **deriva** |
| texto largo (2.400 caracteres) | 536 tokens contra una ventana de 512: **deriva**, porque una respuesta segura sobre texto parcial no vale |
| primitiva no soportada | el modelo declara soportar sólo `noul`; una pregunta `choice` vuelve como `unsupported_by_model` y **deriva**, en vez de inventar una respuesta |

Los casos marcados `[ok]` se afirman: si cambian, el demo lo muestra. El del sarcasmo va con `[·]`
porque **no se afirma**: el modelo puede acertarlo o no según el texto, y lo que importa es que si
duda, derive. Afirmarlo haría que el demo dependiera de la confianza de un caso puntual.

## Salida real

Esta transcripción es la salida de `bash scripts/demo.sh`, copiada tal cual (no retipeada). El script
imprime en inglés:

```text
=== starting the service on 8091 with config.demo.yaml
    the first time it downloads Cardiff XLM-R (~1.1 GB) from Hugging Face

model served: cardiff-xlmr (transformers) | routing: {'noul': 'cardiff-xlmr'}
confidence thresholds: {'noul': 0.75, 'choice': 0.75, 'score': 0.75} | neutral mass: 0.7

  [ok] clear positive                     local    value=True     conf=0.985 (raw) neutral=0.05 model=cardiff-xlmr
  [ok] clear negative                     local    value=False    conf=0.988 (raw) neutral=0.05 model=cardiff-xlmr
  [·] sarcasm                            DELEGATE value=True     conf=0.680 (raw) neutral=0.21 model=cardiff-xlmr
        reason: raw_confidence_below_0.75(0.680);no_temperature_for_noul
  [ok] neutral (high neutral mass)        DELEGATE value=True     conf=0.768 (raw) neutral=0.81 model=cardiff-xlmr
        reason: high_neutral_mass(0.809>0.7)
  [ok] no content                         DELEGATE value=False    conf=0.527 (raw) neutral=0.34 model=cardiff-xlmr
        reason: raw_confidence_below_0.75(0.527);no_temperature_for_noul
  [ok] long: the ending flips the meaning DELEGATE value=True     conf=0.622 (raw) neutral=0.51 model=cardiff-xlmr
        reason: input_truncated(536 tokens > 512);raw_confidence_below_0.75(0.622);no_temperature_for_noul
  [ok] primitive the model does not support DELEGATE value=None     conf=0.000 (raw) neutral=  -  model=cardiff-xlmr
        reason: unsupported_by_model(cardiff-xlmr)

=== what was logged (observability)
  requests 21 | answers 21 | delegated 15 (71.4 %)
  reasons: {'raw_confidence_below_0.75': 6, 'high_neutral_mass': 3, 'input_truncated': 3, 'unsupported_by_model': 3}
  models: {'cardiff-xlmr': 21}
  latency: p50 100.09 ms | p95 312.0 ms
  log at: logs/decisions (level excerpt, 7 written, 0 errors)

=== demo finished. To actually leave it running:  make serve
    (or 'bash scripts/demo.sh --keep' so it is not shut down at the end)
```

## Lo que el demo NO muestra

- **La integración con el agente (DSH)**: el plugin existe en `dsh-laya-plugin/` y está verificado
  contra este mismo servicio, pero DSH no es público, así que esa parte no es reproducible por un
  tercero. Se documenta como integración opcional.
- **Los adaptadores de Laya** (`laya`, `laya-coreml`): necesitan rutas locales o descargas más
  pesadas, y el camino CoreML requiere macOS con Apple Silicon. Con `make setup-full` y el registro
  completo (`config.yaml`) se habilitan, incluido el **enrutamiento por primitiva**: `noul` al
  modelo de sentimiento y `choice`/`score` a un motor de decisión general.
- **La precisión del modelo**: el demo muestra decisiones, no calidad. Las mediciones —incluida la
  comparación contra el baseline que gana— están en `results/SUMMARY_*.md`.

## Verificación automática

```bash
make test      # self-test de los modelos + casos límite + concurrencia
make metrics   # métricas del tráfico registrado
make report    # informe legible
```

</details>
