"""Per-primitive temperature: it is really applied, and what happened is reported.

Key difference from V3/V5: `calibrated=True` no longer means "a calibration file is
loaded", it means "a temperature was applied to this answer". If the primitive has no
fitted T, the answer travels with `calibrated=False` and a note explaining why.
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
    """Returns (confidence, applied, T, note).

    Binary (noul): the logit of P(true) is scaled — which is how the published T was fitted.
    Multiclass (choice/score): softmax(log(p)/T).
    """
    if not probs:
        if fallback is not None:
            return float(fallback), False, None, (
                f"the model exposes no distribution for '{qtype}'; "
                "its confidence is reported as-is, uncalibrated")
        return 0.0, False, None, "no probabilities"
    raw = float(max(probs))
    T = cal.temperatures.get(qtype)
    if T is None:
        return raw, False, None, (
            f"no temperature for '{qtype}'"
            + (f" in {Path(cal.source).name}" if cal.source else " (no calibration file)")
        )
    if T <= 0:
        return raw, False, None, f"invalid temperature ({T})"
    if len(probs) == 2:
        # softmax(logits/T) with two classes = sigma(logit(P(true))/T) for the positive class.
        # CONFIDENCE is the probability of the chosen class, i.e. the max of the calibrated
        # vector: returning plain sigma(z/T) inverted confidence on negative predictions
        # (0.85 raw -> 0.12 "confidence") and triggered false delegations.
        p_true = _sigmoid(_logit(probs[1]) / T)
        return round(max(p_true, 1.0 - p_true), 4), True, T, None
    logp = [math.log(max(p, 1e-12)) / T for p in probs]
    m = max(logp)
    exps = [math.exp(x - m) for x in logp]
    return round(max(exps) / sum(exps), 4), True, T, None
