# Licencias de terceros

Todo lo de esta página está **verificado**, no supuesto: se leyó de los metadatos de los paquetes
instalados, de las tarjetas de los modelos y datasets en caché, y de la API de Hugging Face y de
GitHub. La fecha de verificación es la del último commit de este archivo.

## Paquetes

| Paquete | Licencia | Cómo se verificó |
|---|---|---|
| `laya` | **Apache-2.0** | `importlib.metadata` del paquete instalado |
| `laya-coreml` | **Apache-2.0** | ídem |
| `transformers` | Apache-2.0 | ídem |
| `torch` | BSD-3-Clause + Apache-2.0 + MIT (compuesta) | ídem |
| `fastapi` | MIT | ídem |
| `pydantic`, `uvicorn`, `pyyaml`, `numpy`, `pandas`, `pyarrow`, `safetensors`, `sentencepiece` | permisivas (MIT / BSD / Apache-2.0) | ídem |

## Modelos

| Modelo | Licencia | Cómo se verificó |
|---|---|---|
| `convaiinnovations/laya-multilingual` | Apache-2.0 | tarjeta del modelo en la caché local |
| `cardiffnlp/twitter-xlm-roberta-base-sentiment` | **sin licencia declarada** en la API de HF | API de Hugging Face |
| `Ramg77/laya-sentiment-multilingual` (nuestro fine-tune) | Apache-2.0 (heredada del base) | tarjeta publicada |

`cardiffnlp/twitter-xlm-roberta-base-sentiment` no declara licencia. Se usa **descargándolo del Hub**
(no se redistribuye), que es la práctica habitual, pero conviene tenerlo presente: si alguien
redistribuye este repo con el modelo incluido, está redistribuyendo algo sin licencia explícita.

## Datos

El conjunto de evaluación (`data/test_extended.jsonl`) se construyó desde
`tyqiangz/multilingual-sentiments`, que declara **Apache-2.0** (verificado en su tarjeta y en la API).
Su contenido es idéntico al benchmark `cardiffnlp/tweet_sentiment_multilingual`, que **no declara
licencia**, y la procedencia última son tres proyectos de anotación con sus propias condiciones:

| Idioma | Origen |
|---|---|
| Inglés | SemEval-2017 Task 4 |
| Alemán | SB-10K |
| Español | InterTASS 2017 (6 clases colapsadas a 3) |

**Implicación**: la fuente directa es Apache-2.0 y se redistribuye con atribución, pero la cadena de
procedencia tiene condiciones propias y no está del todo documentada aguas arriba. Si esto se usa con
fines comerciales, conviene revisarlo antes.

## Nuestra licencia: Apache-2.0

El código de este repo se distribuye bajo **Apache-2.0** (ver `LICENSE`).

**Por qué no GPL-2.0.** La intención inicial fue usar GPL-2.0 para acompañar el camino del proyecto
Laya, pero al verificarlo apareció que Laya —tanto su repositorio en GitHub como los paquetes
`laya` y `laya-coreml`— declara **Apache-2.0**, no GPL. Además la FSF considera **Apache-2.0
incompatible con GPL-2.0** (por la cláusula de terminación de patentes), aunque sí compatible con
GPL-3.0. Distribuir este harness bajo GPL-2.0 mientras importa bibliotecas Apache-2.0 (`laya`,
`transformers`, `torch`) habría quedado en una zona gris.

Apache-2.0 es la licencia de Laya, es compatible con todas las dependencias y es la que mejor
describe la intención original: seguir el mismo camino que el motor que este harness integra.

Nada del código cambia por esta decisión; sólo `LICENSE`, esta página y el campo `license` de
`pyproject.toml`.
