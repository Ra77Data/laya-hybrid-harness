"""Temperatura por primitiva: se aplica de verdad y se reporta lo que pasó.

Diferencia clave con V3/V5: `calibrated=True` ya no significa "hay un archivo de
calibración cargado", significa "a esta respuesta se le aplicó una temperatura".
Si la primitiva no tiene T ajustada, la respuesta viaja con `calibrated=False` y una
nota que lo explica.
"""
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

EPS = 1e-6


def _logit(p: float) -> float:
    p = min(max(p, EPS), 1 - EPS)
    return math.log(p / (1 - p))


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


@dataclass
class Calibration:
    loaded: bool = False
    version: int = 0
    method: str = ""
    temperatures: dict = field(default_factory=dict)
    source: str | None = None

    def as_dict(self) -> dict:
        return {
            "loaded": self.loaded,
            "version": self.version,
            "method": self.method,
            "source": self.source,
            "temperatures": self.temperatures,
            "types_with_temperature": sorted(self.temperatures),
        }


def load_calibration(path: str | Path | None) -> Calibration:
    if not path:
        return Calibration()
    p = Path(path)
    if not p.exists():
        return Calibration()
    d = json.loads(p.read_text(encoding="utf-8"))
    temps: dict[str, float] = {}
    for qtype, spec in (d.get("types") or {}).items():
        t = spec.get("T") if isinstance(spec, dict) else spec
        if t:
            temps[str(qtype)] = float(t)
    if "T" in d:
        temps.setdefault("default", float(d["T"]))
    return Calibration(loaded=bool(temps), version=int(d.get("version", 0) or 0),
                       method=str(d.get("method", "")), temperatures=temps, source=str(p))


def apply_temperature(probs: list[float], qtype: str, cal: Calibration, fallback: float | None = None):
    """Devuelve (confianza, aplicada, T, nota).

    Binario (noul): se escala el logit de P(true) — que es como se ajustó la T publicada.
    Multiclase (choice/score): softmax(log(p)/T).
    """
    if not probs:
        if fallback is not None:
            return float(fallback), False, None, (
                f"el modelo no expone distribución para '{qtype}'; "
                "se reporta su confianza tal cual, sin calibrar")
        return 0.0, False, None, "sin probabilidades"
    raw = float(max(probs))
    T = cal.temperatures.get(qtype)
    if T is None:
        return raw, False, None, (
            f"sin temperatura para '{qtype}'"
            + (f" en {Path(cal.source).name}" if cal.source else " (no hay archivo de calibración)")
        )
    if T <= 0:
        return raw, False, None, f"temperatura inválida ({T})"
    if len(probs) == 2:
        # softmax(logits/T) con dos clases = sigma(logit(P(true))/T) para la clase positiva.
        # La CONFIANZA es la probabilidad de la clase elegida, o sea el máximo del vector
        # calibrado: devolver sigma(z/T) a secas invertía la confianza en las predicciones
        # negativas (0,85 crudo -> 0,12 "confianza") y disparaba derivaciones falsas.
        p_true = _sigmoid(_logit(probs[1]) / T)
        return round(max(p_true, 1.0 - p_true), 4), True, T, None
    logp = [math.log(max(p, 1e-12)) / T for p in probs]
    m = max(logp)
    exps = [math.exp(x - m) for x in logp]
    return round(max(exps) / sum(exps), 4), True, T, None
