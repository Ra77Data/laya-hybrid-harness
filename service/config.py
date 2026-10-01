"""Loads and validates the model registry and the routing by primitive."""
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
        # `weights` can be a local path (which must exist) or a Hugging Face repo (resolved
        # through the cache or the network). Only paths used to be accepted.
        # A registry entry can point at a model that is not on this machine: that is not a
        # configuration error, it is an unavailable model. This used to raise, and **the service
        # would not start on any machine other than the author's**, which is exactly the opposite
        # of what is needed for someone else to try it. If something routes to an absent model,
        # the answer says so (`model_unavailable`).
        if (w.startswith("/") or w.startswith("~") or w.startswith(".")) and not Path(w).expanduser().exists():
            self.available = False
            self.unavailable_reason = f"weights path does not exist: {w}"
        # Same logic as with the weights: if the calibration file is missing, the model is not
        # available on this machine, but that cannot stop the service from starting. It used to
        # raise, and with the published template (EDITAR paths) `make test` failed in a fresh clone
        # because of a model nobody was going to serve.
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
    # Model lifecycle. 0 means "never unload": every routed model stays resident, which is what a
    # shared instance wants. On a personal machine the models cost ~1.75 GB and can sit unused for
    # days, so unloading them after an idle period trades memory for a slow first call.
    idle_unload_seconds: int = 0
    idle_check_seconds: int = 60

    def threshold_for(self, qtype: str) -> float:
        return float(self.per_type.get(qtype, self.default_threshold))

    def spec(self, model_id: str | None = None) -> ModelSpec:
        mid = model_id or self.active
        if mid not in self.models:
            raise KeyError(f"model '{mid}' is not in the registry")
        return self.models[mid]

    def model_for(self, qtype: str) -> str:
        """Which model serves this primitive. Without an explicit route, it falls back to the active model."""
        return self.routing.get(qtype, self.active)


def load_config(path: str | Path | None = None) -> Config:
    p = Path(path or os.environ.get("LAYA_CONFIG") or DEFAULT_CONFIG)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    models = {mid: ModelSpec(id=mid, **spec) for mid, spec in raw["models"].items()}
    for m in models.values():
        m.validate()

    # The registry path is resolved against the config's directory, not the cwd: otherwise
    # `report_decisions.py --config <other>/config.yaml` read a different folder and returned zero
    # records with no error at all.
    obs = dict(raw.get("observability") or {})
    if obs.get("directory") and not Path(str(obs["directory"])).is_absolute():
        obs["directory"] = str((p.parent / str(obs["directory"])).resolve())

    deleg = raw.get("delegation", {}) or {}
    life = raw.get("lifecycle", {}) or {}
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

    # Every primitive that will be asked for has to have its model preloaded. Loading takes 2.7-7 s
    # and the DSH plugin gives up at 2.5 s, so a routed-but-lazy model fails the FIRST real request —
    # and it fails on the client side, where nothing points back at the config. That is a static
    # mistake, so it is caught here instead of surfacing later as a mysterious timeout. The check
    # covers the routing fallback too: a primitive with no explicit route is served by `active`.
    for qtype in PRIMITIVES:
        mid = routing.get(qtype) or active
        if mid not in preload:
            raise ValueError(
                f"'{qtype}' is served by '{mid}', which is not in `preload`. Add it: loading takes "
                f"seconds and the first '{qtype}' request would time out on the client side. "
                f"Current preload: {preload}")

    # LAYA_PORT allows running an instance on another port without touching the config (the demo uses it).
    port = int(os.environ.get("LAYA_PORT") or raw["service"]["port"])
    return Config(
        host=raw["service"]["host"], port=port,
        default_threshold=float(deleg.get("default_threshold", 0.75)),
        per_type={k: float(v) for k, v in (deleg.get("per_type") or {}).items()},
        models=models, active=active, routing=routing, preload=preload,
        neutral_mass_threshold=(float(deleg["neutral_mass_threshold"])
                                if deleg.get("neutral_mass_threshold") is not None else None),
        observability=obs,
        idle_unload_seconds=max(0, int(life.get("unload_after_idle_seconds", 0) or 0)),
        idle_check_seconds=max(1, int(life.get("check_interval_seconds", 60) or 60)))
