# El motor general restaurado, y lo que mide

El servicio V7 enruta cada primitiva a un modelo distinto. Ahora mismo:

| Primitiva | Modelo | Por qué |
|---|---|---|
| `noul` (sentimiento) | `cardiff-xlmr` | el mejor medido: 91,67 % en la muestra de 240 |
| `choice` (clasificar/elegir) | `laya-base` | motor general zero-shot |
| `score` (urgencia/escala) | `laya-base` | ídem |

Una sola llamada HTTP puede llevar las tres, y cada respuesta dice con qué modelo se contestó
(`model_used`). Medido contra el servicio desplegado:

| Pregunta | Modelo | Respuesta | Confianza | ¿Deriva? |
|---|---|---|---|---|
| ¿Sentimiento positivo? (`noul`) | `cardiff-xlmr` | `false` | 0,9693 | no |
| ¿Qué equipo debe atenderlo? (`choice`) | `laya-base` | `billing` | 0,9965 | no |
| ¿Qué urgencia tiene? (`score`) | `laya-base` | `media` | 0,4862 | **sí** (umbral 0,70) |

## La formulación importa más que el modelo

Mismo motor (`laya-base`), misma tarea (sentimiento), misma muestra de 240 textos:

| Formulación | Accuracy | Confianza media | Latencia mediana |
|---|---|---|---|
| `choice` con opciones [positive, negative] | **87,50 %** | 0,9338 | 19 ms |
| `noul` ("¿expresa sentimiento positivo?") | **53,33 %** | 0,9632 | 18 ms |

El 53,33 % no es ruido: en seis textos de control (tres claramente positivos, tres claramente
negativos) el modelo **contestó `false` a los seis** con P(true) entre 0,00 y 0,25 — incluido
"I love this product, it changed my life!". Como la muestra está balanceada, responder siempre "no"
da ~50 %. Con la formulación `choice`, esos mismos seis los acierta todos con probabilidad 1,00.

La lectura honesta: el modelo base **no responde bien esa pregunta concreta en formato noul**, muy
probablemente porque la fraseo no se parece a lo que vio durante su entrenamiento. Los modelos
fine-tuneados (v1, v2) sí, porque se entrenaron exactamente con ese fraseo. No es un problema del
adaptador: se verificó contra la respuesta cruda del modelo.

## Comparación en la misma muestra (240 textos, 80 por idioma)

| Modelo | Formulación | Accuracy | Accuracy local | Cobertura local |
|---|---|---|---|---|
| `cardiff-xlmr` | noul | **91,67 %** | 95,28 % | 88 % |
| `laya-base` (zero-shot) | choice | **87,50 %** | 88,84 % | 93 % |
| `laya-sentiment-v1` (fine-tune) | noul | 84,58 % | 89,35 % | 90 % |
| `laya-sentiment-v2` (fine-tune 4,8×) | noul | 83,75 % | 85,17 % | 98 % |
| `laya-base` (zero-shot) | noul | 53,33 % | 53,28 % | 95 % |

**Un motor general zero-shot, sin ningún entrenamiento, supera al modelo fine-tuneado de este
proyecto en la misma tarea** (87,5 % contra 84,6 % en esta muestra). Es la misma conclusión que dio
el aislamiento dato/receta, ahora con otra evidencia: el fine-tune no aportaba lo que se creía.

## Coste de la carga perezosa

El modelo general tarda ~2,7 s en cargar y el plugin de DSH corta a 2,5 s: con carga perezosa, la
primera pregunta de tipo `choice` habría fallado por timeout. Por eso `preload` incluye los dos
modelos que sirven alguna primitiva. En caliente, la latencia es ~19-26 ms por pregunta.

## Cómo se verifica

```bash
curl -s http://127.0.0.1:8090/health | python3 -m json.tool   # routing y estado por modelo
curl -s -X POST http://127.0.0.1:8090/selftest | python3 -m json.tool   # los 5 modelos
python scripts/battery_choice.py --type choice --options positive,negative
python scripts/battery_choice.py --type noul --model laya-base   # fija el modelo, salta el routing
```
