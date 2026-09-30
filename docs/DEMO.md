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

Esta transcripción es la salida de `bash scripts/demo.sh`, copiada tal cual (no retipeada):

```text
=== arrancando el servicio en 8091 con config.demo.yaml
    la primera vez descarga Cardiff XLM-R (~1,1 GB) desde Hugging Face

modelo servido: cardiff-xlmr (transformers) | routing: {'noul': 'cardiff-xlmr'}
umbral de confianza: {'noul': 0.75, 'choice': 0.75, 'score': 0.75} | masa neutral: 0.7

  [ok] positivo claro                     local  value=True     conf=0.985 (cruda) neutral=0.05 modelo=cardiff-xlmr
  [ok] negativo claro                     local  value=False    conf=0.988 (cruda) neutral=0.05 modelo=cardiff-xlmr
  [·] sarcasmo                           DERIVA value=True     conf=0.680 (cruda) neutral=0.21 modelo=cardiff-xlmr
        motivo: raw_confidence_below_0.75(0.680);no_temperature_for_noul
  [ok] neutro (masa neutral alta)         DERIVA value=True     conf=0.768 (cruda) neutral=0.81 modelo=cardiff-xlmr
        motivo: high_neutral_mass(0.809>0.7)
  [ok] sin contenido                      DERIVA value=False    conf=0.527 (cruda) neutral=0.34 modelo=cardiff-xlmr
        motivo: raw_confidence_below_0.75(0.527);no_temperature_for_noul
  [ok] largo: el final cambia el sentido  DERIVA value=True     conf=0.622 (cruda) neutral=0.51 modelo=cardiff-xlmr
        motivo: input_truncated(536 tokens > 512);raw_confidence_below_0.75(0.622);no_temperature_for_noul
  [ok] primitiva que el modelo no soporta DERIVA value=None     conf=0.000 (cruda) neutral=  -  modelo=cardiff-xlmr
        motivo: unsupported_by_model(cardiff-xlmr)

=== lo que quedó registrado (observabilidad)
  peticiones 21 | respuestas 21 | derivadas 15 (71.4 %)
  motivos: {'raw_confidence_below_0.75': 6, 'high_neutral_mass': 3, 'input_truncated': 3, 'unsupported_by_model': 3}
  modelos: {'cardiff-xlmr': 21}
  latencia: p50 99.98 ms | p95 310.09 ms
  registro en: /Users/cesarmg.data/Documents/deepseek-harness/Default workspace/harness/logs/decisions (nivel excerpt, 7 escritos, 0 errores)

=== demo terminado. Para dejarlo corriendo de verdad:  make serve
    (o 'bash scripts/demo.sh --keep' para que no lo apague al terminar)
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
  comparación contra el baseline que gana— están en `results/RESUMEN_*.md`.

## Verificación automática

```bash
make test      # self-test de los modelos + casos límite + concurrencia
make metrics   # métricas del tráfico registrado
make report    # informe legible
```
