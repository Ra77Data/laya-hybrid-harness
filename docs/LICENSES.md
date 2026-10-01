# Third-party licenses

Everything on this page is **verified**, not assumed: it was read from the metadata of the installed
packages, from the model and dataset cards in the local cache, and from the Hugging Face and GitHub
APIs. The verification date is that of the last commit touching this file.

## Packages

| Package | License | How it was verified |
|---|---|---|
| `laya` | **Apache-2.0** | `importlib.metadata` of the installed package |
| `laya-coreml` | **Apache-2.0** | same |
| `transformers` | Apache-2.0 | same |
| `torch` | BSD-3-Clause + Apache-2.0 + MIT (composite) | same |
| `fastapi` | MIT | same |
| `pydantic`, `uvicorn`, `pyyaml`, `numpy`, `pandas`, `pyarrow`, `safetensors`, `sentencepiece` | permissive (MIT / BSD / Apache-2.0) | same |

## Models

| Model | License | How it was verified |
|---|---|---|
| `convaiinnovations/laya-multilingual` | Apache-2.0 | model card in the local cache |
| `cardiffnlp/twitter-xlm-roberta-base-sentiment` | **no license declared** in the HF API | Hugging Face API |
| `Ramg77/laya-sentiment-multilingual` (this project's fine-tune) | Apache-2.0 (inherited from the base) | published card |

`cardiffnlp/twitter-xlm-roberta-base-sentiment` declares no license. It is used **by downloading it
from the Hub** (not redistributed), which is common practice, but it is worth keeping in mind: anyone
redistributing this repo with the model included is redistributing something with no explicit license.

## Data

The evaluation set (`data/test_extended.jsonl`) was built from `tyqiangz/multilingual-sentiments`,
which declares **Apache-2.0** (verified in its card and in the API). Its content is identical to the
`cardiffnlp/tweet_sentiment_multilingual` benchmark, which **declares no license**, and the ultimate
provenance is three annotation projects with their own terms:

| Language | Origin |
|---|---|
| English | SemEval-2017 Task 4 |
| German | SB-10K |
| Spanish | InterTASS 2017 (6 classes collapsed to 3) |

**Implication**: the direct source is Apache-2.0 and is redistributed with attribution, but the chain
of provenance carries its own terms and is not fully documented upstream. If this is used
commercially, it is worth reviewing first.

## This repository's license: Apache-2.0

The code in this repository is distributed under **Apache-2.0** (see `LICENSE`).

**Why not GPL-2.0.** The initial intent was to use GPL-2.0 to follow the Laya project's path, but on
verifying it, Laya —both its GitHub repository and the `laya` and `laya-coreml` packages— declares
**Apache-2.0**, not GPL. On top of that, the FSF considers **Apache-2.0 incompatible with GPL-2.0**
(because of the patent-termination clause), though compatible with GPL-3.0. Distributing this harness
under GPL-2.0 while it imports Apache-2.0 libraries (`laya`, `transformers`, `torch`) would have
landed in a grey area.

Apache-2.0 is Laya's license, it is compatible with every dependency, and it best describes the
original intent: to follow the same path as the engine this harness integrates.

Nothing in the code changes because of this decision; only `LICENSE`, this page and the `license`
field in `pyproject.toml`.

---

<details>
<summary><h2>🇪🇸 Versión en Español — Haz clic aquí para desplegar</h2></summary>

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

</details>
