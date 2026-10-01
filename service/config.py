"""Carga y valida el registro de modelos y el enrutamiento por primitiva."""
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
DEFAULT_CONFIG = HERE.parent / "config.yaml"

ADAPTERS = {"coreml", "laya", "transformers"}
PRIMITIVES = {"noul", "choice", "score"}


@dataclass
class ModelSpec:
    id: str
    adapter: str
    supports: set[str]
    weights: str
    expect_sha256: str | None = None
    calibration: str | None = None
    revision: str | None = None
    label: str = ""
    smoke: list[dict] = field(default_factory=list)
    binary_reduction: dict | None = None
    max_length: int | None = None      # ventana del tokenizador para este adaptador
    available: bool = True             # False si los pesos no están en esta máquina
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        self.supports = set(self.supports or [])
        self.smoke = list(self.smoke or [])
        self.expect_sha256 = self.expect_sha256 or None
        self.calibration = self.calibration or None
        self.revision = self.revision or None

    def validate(self) -> None:
        if self.adapter not in ADAPTERS:
            raise ValueError(f"{self.id}: unknown adapter '{self.adapter}'")
        bad = self.supports - PRIMITIVES
        if bad:
            raise ValueError(f"{self.id}: invalid primitives {bad}")
        w = str(self.weights)
        # `weights` puede ser una ruta local (debe existir) o un repo de Hugging Face (se resuelve
        # por la caché o la red). Antes solo se aceptaban rutas.
        # Una entrada del registro puede apuntar a un modelo que no está en esta máquina: no es un
        # error de configuración, es un modelo no disponible. Antes esto levantaba y **el servicio
        # no arrancaba en una máquina que no fuera la del autor**, que es exactamente lo contrario
        # de lo que hace falta para que alguien más pueda probarlo. Si alguien enruta a un modelo
        # ausente, la respuesta lo dice (`model_unavailable`).
        if (w.startswith("/") or w.startswith("~") or w.startswith(".")) and not Path(w).expanduser().exists():
            self.available = False
            self.unavailable_reason = f"weights path does not exist: {w}"
        # Misma lógica que con los pesos: si falta el archivo de calibración, el modelo no está
        # disponible en esta máquina, pero eso no puede impedir que el servicio arranque. Antes
        # levantaba, y con la plantilla publicada (rutas EDITAR) `make test` fallaba en un clon
        # nuevo por un modelo que nadie iba a servir.
        if self.calibration and not Path(self.calibration).exists():
            self.available = False
            self.unavailable_reason = f"calibration file does not exist: {self.calibration}"
        for case in self.smoke:
            if case.get("type") not in self.supports:
                raise ValueError(
                    f"{self.id}: el caso de self-test usa '{case.get('type')}', "
                    f"that the model does not declare support for ({sorted(self.supports)})")


@dataclass
class Config:
    host: str
    port: int
    default_threshold: float
    per_type: dict[str, float]
    models: dict[str, ModelSpec]
    active: str
    routing: dict[str, str] = field(default_factory=dict)
    preload: list[str] = field(default_factory=list)
    neutral_mass_threshold: float | None = None   # derivar si P(neutro) supera esto
    observability: dict = field(default_factory=dict)

    def threshold_for(self, qtype: str) -> float:
        return float(self.per_type.get(qtype, self.default_threshold))

    def spec(self, model_id: str | None = None) -> ModelSpec:
        mid = model_id or self.active
        if mid not in self.models:
            raise KeyError(f"model '{mid}' is not in the registry")
        return self.models[mid]

    def model_for(self, qtype: str) -> str:
        """Qué modelo sirve esta primitiva. Sin ruta explícita, cae al modelo activo."""
        return self.routing.get(qtype, self.active)


def load_config(path: str | Path | None = None) -> Config:
    p = Path(path or os.environ.get("LAYA_CONFIG") or DEFAULT_CONFIG)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    models = {mid: ModelSpec(id=mid, **spec) for mid, spec in raw["models"].items()}
    for m in models.values():
        m.validate()

    # La ruta del registro se resuelve contra el directorio del config, no contra el cwd: si no,
    # `report_decisions.py --config <otro>/config.yaml` leía una carpeta distinta y devolvía cero
    # registros sin ningún error.
    obs = dict(raw.get("observability") or {})
    if obs.get("directory") and not Path(str(obs["directory"])).is_absolute():
        obs["directory"] = str((p.parent / str(obs["directory"])).resolve())

    deleg = raw.get("delegation", {}) or {}
    active = os.environ.get("LAYA_ACTIVE_MODEL") or raw.get("active") or next(iter(models))
    if active not in models:
        raise KeyError(f"active model '{active}' is not in the registry")

    routing = {str(k): str(v) for k, v in (raw.get("routing") or {}).items()}
    for qtype, mid in routing.items():
        if qtype not in PRIMITIVES:
            raise ValueError(f"routing: unknown primitive '{qtype}'")
        if mid not in models:
            raise ValueError(f"routing: '{qtype}' points at '{mid}', which is not in the registry")
        if qtype not in models[mid].supports:
            raise ValueError(
                f"routing: '{qtype}' apunta a '{mid}', que declara soportar {sorted(models[mid].supports)}")

    preload = [str(x) for x in (raw.get("preload") or [active])]
    for mid in preload:
        if mid not in models:
            raise ValueError(f"preload: '{mid}' is not in the registry")

    # LAYA_PORT permite correr una instancia en otro puerto sin tocar la config (lo usa el demo).
    port = int(os.environ.get("LAYA_PORT") or raw["service"]["port"])
    return Config(
        host=raw["service"]["host"], port=port,
        default_threshold=float(deleg.get("default_threshold", 0.75)),
        per_type={k: float(v) for k, v in (deleg.get("per_type") or {}).items()},
        models=models, active=active, routing=routing, preload=preload,
        neutral_mass_threshold=(float(deleg["neutral_mass_threshold"])
                                if deleg.get("neutral_mass_threshold") is not None else None),
        observability=obs)
