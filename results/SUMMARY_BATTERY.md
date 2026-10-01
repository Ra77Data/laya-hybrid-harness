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
   está dando ventaja de latencia en textos cortos a través de este wrapper. El "16 ms" que figura
   en la documentación de V5 no se reproduce aquí y conviene re-medirlo con su método original.
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
