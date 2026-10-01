"""Adaptadores de modelo. Todos exponen la misma interfaz y devuelven la misma forma canónica.

    backend.load()
    backend.weights_info() -> {"path", "sha256", "expected", "match", "note"}
    backend.predict(state, questions) -> {qid: {"type", "probs", "value", "options"}}

El servicio no conoce ningún modelo: solo pide un adaptador por nombre en la config.
"""
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("USE_TF", "0")            # evita el deadlock de abseil al cargar Laya
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# HF_HUB_OFFLINE y HF_HUB_CACHE se dejan al entorno: fijarlos acá escondía el fallo
# "el modelo no está en la caché y no puedo bajarlo" detrás de un error de red.


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def resolve_weights(weights: str, filenames: tuple[str, ...]) -> tuple[str | None, str | None, str]:
    """Devuelve (ruta, sha256 real, nota) para un path local o un repo de HF ya cacheado.

    El nombre del blob en la caché de Hugging Face **no** es el sha256 del contenido (se
    verificó: difieren para los dos modelos). Reportar aquel como sha256 era incorrecto, así
    que acá se hashea el archivo de verdad, que es 1-2 s por modelo y hace que `expect_sha256`
    signifique algo.
    """
    p = Path(weights)
    if p.is_dir():
        for f in filenames:
            fp = p / f
            if fp.exists():
                return str(fp), sha256_file(fp), f"sha256 computed over {f}"
        return None, None, f"none of {filenames} found in {p}"
    if p.is_file():
        return str(p), sha256_file(p), f"sha256 computed over {p.name}"
    try:
        from huggingface_hub import try_to_load_from_cache
        for f in filenames:
            cp = try_to_load_from_cache(weights, f)
            if isinstance(cp, str) and Path(cp).exists():
                return cp, sha256_file(Path(cp)), f"sha256 computed over {f}, resolved from the cache"
    except Exception as exc:  # noqa: BLE001
        return None, None, f"could not resolve the cache: {type(exc).__name__}"
    return None, None, "the weights file is not in the local cache"


def _laya_question(q: dict) -> dict:
    """Esquema que espera `Agent.predict` / `laya_coreml.predict`.

    Ojo: la librería tiene DOS capas con esquemas distintos para lo mismo. `Agent.predict`
    (alto nivel) usa {"type", "instructions", "criteria"}; `build_sequence` (bajo nivel)
    usa {"t", "ins", "crit"}. Acá se usa la capa de alto nivel; mezclarlas fue el bug que
    rompía `choice` con un AttributeError sobre None.
    """
    out = {"type": q["type"], "instructions": q.get("instructions", "")}
    if q["type"] == "choice":
        out["criteria"] = list(q.get("options") or [])
    elif q["type"] == "score":
        out["criteria"] = list(q.get("scale") or [])
    return out


def _canonical_from_laya(ans: dict, q: dict) -> dict:
    """Normaliza la respuesta cruda de laya / laya-coreml a la forma canónica.

    Laya publica la distribución de `choice` en `probabilities` (un dict opción->prob),
    no en una lista `probs`; y en `score` la distribución viene indexada por número con
    las etiquetas en `legend`. Si no hay distribución, se devuelve `probs` vacío y la
    confianza propia del modelo: antes se fabricaba un vector uniforme, que es
    exactamente el tipo de dato inventado que este servicio debe evitar.
    """
    qtype = ans.get("type") or q["type"]
    if qtype == "noul" or "noul" in ans:
        p = float(ans.get("noul", ans.get("confidence", 0.0)))
        return {"type": "noul", "probs": [round(1 - p, 6), round(p, 6)],
                "value": p >= 0.5, "options": [], "confidence": float(ans.get("confidence", max(p, 1 - p)))}

    probs_dict = ans.get("probabilities") or {}
    if qtype == "choice":
        if probs_dict:
            options = list(probs_dict.keys())
            probs = [float(probs_dict[k]) for k in options]
        else:
            options, probs = [], []
        value = ans.get("choice")
        if value is None and probs:
            value = options[probs.index(max(probs))]
        return {"type": "choice", "probs": probs, "value": value, "options": options,
                "confidence": float(ans.get("confidence", max(probs) if probs else 0.0))}

    if qtype == "score":
        legend = ans.get("legend") or {}
        keys = sorted(probs_dict, key=lambda k: int(k) if str(k).isdigit() else 0)
        probs = [float(probs_dict[k]) for k in keys]
        options = [str(legend.get(str(k), k)) for k in keys]
        value = options[probs.index(max(probs))] if probs and len(probs) == len(options) else None
        return {"type": "score", "probs": probs, "value": value, "options": options,
                "score_raw": ans.get("score"),
                "confidence": float(ans.get("confidence", max(probs) if probs else 0.0))}

    return {"type": qtype, "probs": [], "value": ans.get("value"),
            "options": list(q.get("options") or q.get("scale") or []),
            "confidence": float(ans.get("confidence", 0.0))}


class Backend:
    adapter = "base"

    def __init__(self, spec):
        self.spec = spec
        self._weights: dict = {}

    def load(self) -> None:                      # pragma: no cover - lo implementa cada adaptador
        raise NotImplementedError

    def weights_info(self) -> dict:
        return self._weights

    def predict(self, state: str, questions: list[dict]) -> dict:  # pragma: no cover
        raise NotImplementedError


class CoreMLBackend(Backend):
    """Sirve un paquete CoreML de Laya (ANE/GPU en Apple Silicon)."""
    adapter = "coreml"

    def load(self) -> None:
        import laya_coreml as laya
        self.agent = laya.load(str(self.spec.weights))
        meta = Path(self.spec.weights) / "coreml_config.json"
        declared = None
        if meta.exists():
            declared = (json.loads(meta.read_text(encoding="utf-8")) or {}).get("source_weights_sha256")
        self._weights = {
            "path": str(self.spec.weights),
            "sha256": declared,
            "expected": self.spec.expect_sha256,
            "match": (declared == self.spec.expect_sha256) if (declared and self.spec.expect_sha256) else None,
            "note": "hash de los pesos de origen, declarado en coreml_config.json",
        }

    def predict(self, state: str, questions: list[dict]) -> dict:
        schema = {q["id"]: _laya_question(q) for q in questions}
        raw = self.agent.predict(state, schema)
        usage = raw.get("usage") or {}
        answers = raw.get("answers") or {}
        out = {}
        for q in questions:
            item = _canonical_from_laya(answers.get(q["id"], {}), q)
            # La librería ya dice si tuvo que tirar texto; antes se descartaba.
            item["input_tokens"] = usage.get("input_tokens")
            item["state_tokens_dropped"] = usage.get("state_tokens_dropped")
            item["truncated"] = bool(usage.get("truncated"))
            out[q["id"]] = item
        return out


class LayaBackend(Backend):
    """Sirve un checkpoint Laya en safetensors (sin CoreML): pensado para x86/Linux o CI."""
    adapter = "laya"

    def load(self) -> None:
        import laya.agent

        # La librería trae su propio cargador: batching, renderizado de opciones y parseo de
        # respuestas. La temperatura NO se delega acá: la aplica el servicio, igual para todos
        # los adaptadores, para no calibrar dos veces.
        self.agent = laya.agent.load(str(self.spec.weights))
        path, sha, note = resolve_weights(self.spec.weights, ("model.safetensors",))
        self._weights = {
            "path": path or str(self.spec.weights),
            "sha256": sha,
            "expected": self.spec.expect_sha256,
            "match": (sha == self.spec.expect_sha256) if (sha and self.spec.expect_sha256) else None,
            "note": note,
        }

    def predict(self, state: str, questions: list[dict]) -> dict:
        schema = {q["id"]: _laya_question(q) for q in questions}
        raw = self.agent.predict(state, schema)
        answers = raw.get("answers") or {}
        return {q["id"]: _canonical_from_laya(answers.get(q["id"], {}), q) for q in questions}


class TransformersBackend(Backend):
    """Sirve un clasificador de Hugging Face. Para sentimiento 3 clases se reduce a binario."""
    adapter = "transformers"

    def load(self) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        rev = getattr(self.spec, "revision", None) or None
        self.tok = AutoTokenizer.from_pretrained(self.spec.weights, revision=rev)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.spec.weights, revision=rev)
        self.torch = torch
        self.device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
        self.model.to(self.device).eval()
        self.id2 = {int(k): str(v).lower() for k, v in self.model.config.id2label.items()}
        # 128 tokens era el valor por defecto que yo hardcodeé: un texto de 2.500 caracteres
        # perdía tres cuartos de su contenido sin que nadie se enterara. Ahora es configurable.
        self.max_length = int(self.spec.max_length or 512)
        path, sha, note = resolve_weights(
            self.spec.weights, ("model.safetensors", "pytorch_model.bin"))
        self._weights = {
            "path": path or self.spec.weights,
            "sha256": sha,
            "expected": self.spec.expect_sha256,
            "match": (sha == self.spec.expect_sha256) if (sha and self.spec.expect_sha256) else None,
            "note": note + (f" | pinned revision: {rev}" if rev else " | sin revision fijada"),
        }

    def predict(self, state: str, questions: list[dict]) -> dict:
        import torch

        red = self.spec.binary_reduction or {}
        pos, neg = red.get("positive"), red.get("negative")
        out = {}
        text = " ".join("@user" if w.startswith("@") and len(w) > 1 else ("http" if w.startswith("http") else w)
                        for w in state.split(" "))
        n_tokens = len(self.tok(text, add_special_tokens=False)["input_ids"])
        truncated = n_tokens > self.max_length
        enc = self.tok(text, truncation=True, max_length=self.max_length, return_tensors="pt").to(self.device)
        with torch.no_grad():
            probs3 = torch.softmax(self.model(**enc).logits, -1).float().cpu().numpy()[0].tolist()
        for q in questions:
            if q["type"] != "noul" or pos is None or neg is None:
                out[q["id"]] = {"type": q["type"], "probs": [], "value": None, "options": [],
                                "unsupported": True}
                continue
            denom = max(probs3[pos] + probs3[neg], 1e-9)
            p = probs3[pos] / denom
            out[q["id"]] = {"type": "noul", "probs": [round(1 - p, 6), round(p, 6)],
                            "value": p >= 0.5, "options": [], "neutral_mass": round(probs3[1], 4),
                            "input_tokens": n_tokens, "max_length": self.max_length,
                            "truncated": truncated}
        return out


ADAPTER_MODULES = {
    "coreml": ("laya_coreml", "torch"),
    "laya": ("laya", "torch"),
    "transformers": ("torch", "transformers"),
}


def adapter_status(adapter: str) -> tuple[bool, str | None]:
    """¿Está instalado el runtime que este adaptador necesita?

    Tercera dimensión, además de "los pesos existen": un modelo puede tener sus pesos y aun así no
    poder servirse porque el paquete del adaptador no está instalado. En una instalación `[demo]`
    eso pasaba con los cuatro modelos de Laya, y el self-test los reportaba como fallados cuando lo
    único que faltaba era `make setup-full`.
    """
    import importlib.util
    faltan = [m for m in ADAPTER_MODULES.get(adapter, ()) if importlib.util.find_spec(m) is None]
    if faltan:
        return False, (f"the '{adapter}' adapter needs {' and '.join('`' + m + '`' for m in faltan)}: "
                       "install the full extra (make setup-full)")
    return True, None


def build_backend(spec) -> Backend:
    return {"coreml": CoreMLBackend, "laya": LayaBackend, "transformers": TransformersBackend}[spec.adapter](spec)
