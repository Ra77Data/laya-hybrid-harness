# Pipeline battery: three models, one service

Same service, same 240 texts (80 per language, a deterministic seed=42 sample from the non-neutral
test set), same thresholds. The only thing that changed between runs was `LAYA_ACTIVE_MODEL`. Not a
line of code was touched between models.

| Model | Accuracy (n=240) | **Local accuracy** (coverage) | Mean confidence | Latency med/p95 | T applied |
|---|---|---|---|---|---|
| `cardiff-xlmr` | **91.67%** [87.5-94.5] | **95.28%** [91.5-97.4] over 88% | 0.9106 | **10 / 103 ms** | none |
| `laya-sentiment-v1` | 84.58% [79.5-88.6] | 89.35% [84.5-92.8] over 90% | 0.8950 | 55 / 143 ms | 0.9 |
| `laya-sentiment-v2` | 83.75% [78.6-87.9] | 85.17% [80.1-89.1] over 98% | 0.8947 | 19 / 27 ms | 1.35 |

Paired comparison against v1 on the same texts (exact McNemar):

| Model | v1 alone right | the other alone right | p |
|---|---|---|---|
| `cardiff-xlmr` | 8 | 25 | **4.6e-03** |
| `laya-sentiment-v2` | 13 | 11 | 0.84 |

By language (accuracy): Cardiff 87.5 / 96.2 / 91.2 (de/en/es); v1 77.5 / 90.0 / 86.2; v2 80.0 / 90.0 / 81.2.

## What the pipeline measurement shows (not the model)

1. **Cardiff wins on all three dimensions at once**: accuracy (+7 points), quality of what it answers
   locally (95.3% against 89.4%) and latency (10 ms against 55 ms), without needing calibration. It is
   not a trade-off: it is dominance.
2. **The gate fails in the "delegates too little" direction with overconfident models.** v2 keeps
   **98%** of traffic local —the highest of the three— and is the least accurate of the three. Its
   mean raw confidence is 0.9445, and the T=1.35 correction only brings it down to 0.8947: still
   above the threshold. A badly calibrated model is not fixed by temperature when the bias is large.
3. **The CoreML path is the slowest of the three** in this measurement: 55 ms median against 19 ms for
   the same model and architecture served from safetensors through MPS. The ANE conversion is not
   buying a latency advantage on short texts through this wrapper. V5's "16 ms" **was re-measured with
   its own method** (timing `/decide` on the server) and does not reproduce: it is the model, not the
   network. See `docs/VERSIONING.md`.
4. **Honest calibration is visible in the data**: v1 goes from 0.8786 raw to 0.8950 at T=0.9
   (sharpens), v2 from 0.9445 to 0.8947 at T=1.35 (softens), and Cardiff travels with
   `calibrated=false` because it has no temperature. Before, all three would have reported
   `calibrated: true`.

## Limits of this measurement

- 240 texts means 80 per language: the Wilson intervals are in the table and do not allow claiming
  differences smaller than ~4 points. v1's accuracy here (84.58%) is below its 86.0% on the full 1,740,
  consistent with sampling error.
- The texts come from the dataset's test split, not real harness traffic: the test set is cleaner than
  a real ticket or comment.
- Latency includes the local HTTP round trip and preprocessing, not just inference.

## Reproduce

```bash
bash scripts/run_battery_all.sh
```

It generates `results/battery_<model>.json` (with per-text rows), `results/service_<model>.log` and the
comparison table.

---

<details>
<summary><h2>🇪🇸 Versión en Español — Haz clic aquí para desplegar</h2></summary>

# Batería del pipeline: tres modelos, un solo servicio

Mismo servicio, mismos 240 textos (80 por idioma, muestra determinista seed=42 del test no-neutro),
mismos umbrales. Lo único que cambió entre corridas fue `LAYA_ACTIVE_MODEL`. Ninguna línea de
código se tocó entre modelo y modelo.

| Modelo | Accuracy (n=240) | **Accuracy local** (cobertura) | Confianza media | Latencia med/p95 | T aplicada |
|---|---|---|---|---|---|
| `cardiff-xlmr` | **91,67 %** [87,5–94,5] | **95,28 %** [91,5–97,4] sobre 88 % | 0,9106 | **10 / 103 ms** | ninguna |
| `laya-sentiment-v1` | 84,58 % [79,5–88,6] | 89,35 % [84,5–92,8] sobre 90 % | 0,8950 | 55 / 143 ms | 0,9 |
| `laya-sentiment-v2` | 83,75 % [78,6–87,9] | 85,17 % [80,1–89,1] sobre 98 % | 0,8947 | 19 / 27 ms | 1,35 |

Comparación pareada contra v1 en los mismos textos (McNemar exacto):

| Modelo | solo-v1 acierta | solo-el-otro acierta | p |
|---|---|---|---|
| `cardiff-xlmr` | 8 | 25 | **4,6·10⁻³** |
| `laya-sentiment-v2` | 13 | 11 | 0,84 |

Por idioma (accuracy): Cardiff 87,5 / 96,2 / 91,2 (de/en/es); v1 77,5 / 90,0 / 86,2; v2 80,0 / 90,0 / 81,2.

## Lo que muestra la medición del pipeline (no del modelo)

1. **Cardiff gana en las tres dimensiones a la vez**: accuracy (+7 puntos), calidad de lo que se
   responde localmente (95,3 % contra 89,4 %) y latencia (10 ms contra 55 ms), sin necesitar
   calibración. No es un intercambio: es dominancia.
2. **La compuerta falla en la dirección "delega de menos" con modelos sobreconfiados.** v2 conserva
   el **98 %** del tráfico localmente —el más alto de los tres— y es el menos preciso de los tres.
   Su confianza cruda media es 0,9445, y la corrección T=1,35 la baja solo a 0,8947: sigue por
   encima del umbral. Un modelo mal calibrado no se arregla con la temperatura si el sesgo es
   grande.
3. **El camino CoreML es el más lento de los tres** en esta medición: 55 ms de mediana contra 19 ms
   del mismo modelo y misma arquitectura servido en safetensors por MPS. La conversión a ANE no
   está dando ventaja de latencia en textos cortos a través de este wrapper. El "16 ms" de la
   documentación de V5 **se re-midió con su propio método** (cronometrar `/decide` en el servidor) y no
   se reproduce: es el modelo, no la red. Ver `docs/VERSIONING.md`.
4. **La calibración honesta se ve en los datos**: v1 pasa de 0,8786 crudo a 0,8950 con T=0,9
   (afila), v2 de 0,9445 a 0,8947 con T=1,35 (suaviza), y Cardiff viaja con `calibrated=false`
   porque no tiene temperatura. Antes, los tres habrían reportado `calibrated: true`.

## Límites de esta medición

- 240 textos son 80 por idioma: los intervalos de Wilson están en la tabla y no permiten afirmar
  diferencias menores a ~4 puntos. La accuracy de v1 aquí (84,58 %) está por debajo de su 86,0 % en
  los 1.740 completos, consistente con el error de muestreo.
- Los textos son del test del dataset, no tráfico real del harness: el test es más limpio que un
  ticket o un comentario real.
- La latencia incluye el viaje HTTP local y el preprocesado, no solo la inferencia.

## Reproducir

```bash
bash scripts/run_battery_all.sh
```

Genera `results/battery_<modelo>.json` (con las filas por texto), `results/service_<modelo>.log` y
la tabla comparativa.

</details>
