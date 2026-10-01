"""Decision log: the only way to measure the traffic that actually arrives.

Principles, learned the hard way in this project:

  * **Logging never takes a decision down.** Everything runs inside a try/except: a failure
    writing the log cannot become a service failure.
  * **It records what happened, not what should have happened**: calibration version, whether a
    temperature was applied, which model answered and why it delegated.
  * **Privacy by default**: the default level is `metadata`, which keeps numbers, hashes and
    lengths but **not the text**. `excerpt` (first characters) and `full` have to be asked for
    explicitly, and that is what you trade for the ability to label real traffic later.
  * **Daily rotation** and a bounded in-memory window so `/metrics` does not read from disk on
    every request.
"""
import json
import threading
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

LEVELS = ("off", "metadata", "excerpt", "full")


def _kind(reason: str | None) -> str | None:
    """Groups delegation reasons: the numbers inside them prevent counting them."""
    if not reason:
        return None
    return reason.split("(")[0].split(";")[0].strip() or None


def _pct(sorted_vals: list[float], q: float) -> float | None:
    if not sorted_vals:
        return None
    idx = min(len(sorted_vals) - 1, int(round(q * (len(sorted_vals) - 1))))
    return round(sorted_vals[idx], 2)


class DecisionLog:
    def __init__(self, enabled: bool = True, directory: str | Path = "logs/decisions",
                 level: str = "metadata", excerpt_chars: int = 160, window: int = 5000,
                 retain_days: int = 30):
        self.enabled = bool(enabled)
        self.level = level if level in LEVELS else "metadata"
        self.directory = Path(directory)
        self.excerpt_chars = int(excerpt_chars)
        self.retain_days = int(retain_days)
        self._lock = threading.Lock()
        self._recent: deque = deque(maxlen=int(window))
        self._written = 0
        self._errors = 0
        if self.enabled and self.level != "off":
            self.directory.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ writing
    def _file(self, when: datetime) -> Path:
        return self.directory / f"decisions-{when:%Y-%m-%d}.jsonl"

    def record(self, *, state: str, questions: list[dict], answers: list[dict],
               latency_ms: float, model: str, calibration_version: int,
               routing: dict | None = None) -> None:
        try:
            now = datetime.now(timezone.utc)
            ans = []
            for a in answers:
                ans.append({
                    "id": a.get("id"), "type": a.get("type"), "model": a.get("model_used"),
                    "value": a.get("value"), "confidence": a.get("confidence"),
                    "raw_confidence": a.get("raw_confidence"), "calibrated": a.get("calibrated"),
                    "temperature": a.get("temperature"), "threshold": a.get("threshold"),
                    "neutral_mass": a.get("neutral_mass"), "truncated": a.get("truncated"),
                    "input_tokens": a.get("input_tokens"),
                    "supported": a.get("supported"), "delegate": a.get("delegate_to_cloud"),
                    "delegate_kind": _kind(a.get("delegate_reason")),
                    "delegate_reason": a.get("delegate_reason")})
            rec = {
                "ts": now.isoformat(timespec="seconds"),
                "request": {
                    "chars": len(state or ""),
                    "questions": len(questions),
                    "types": sorted({q.get("type") for q in questions}),
                    "lang_guess": _lang_guess(state),
                    "sha256_8": _short_hash(state),
                    "state": (state if self.level == "full"
                              else (state[: self.excerpt_chars] if self.level == "excerpt" else None)),
                },
                "answers": ans,
                "latency_ms": latency_ms,
                "model_active": model,
                "calibration_version": calibration_version,
                "routing": routing or {},
            }
            with self._lock:
                self._recent.append(rec)
                if self.enabled and self.level != "off":
                    with open(self._file(now), "a", encoding="utf-8") as f:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    self._written += 1
        except Exception:  # noqa: BLE001
            # Logging can never take a decision down: count it and carry on.
            self._errors += 1

    # ------------------------------------------------------------------ metrics
    def _read(self, hours: float) -> list[dict]:
        if not self.directory.exists():
            return []
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        out = []
        for path in sorted(self.directory.glob("decisions-*.jsonl")):
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if rec.get("ts", "") >= since.isoformat(timespec="seconds"):
                            out.append(rec)
            except OSError:
                continue
        return out

    def metrics(self, hours: float = 24) -> dict:
        recs = self._read(hours)
        answers = [a for r in recs for a in r.get("answers", [])]
        lat = sorted(r["latency_ms"] for r in recs if isinstance(r.get("latency_ms"), (int, float)))

        def hist(values, edges):
            out = {}
            for i, lo in enumerate(edges):
                hi = edges[i + 1] if i + 1 < len(edges) else None
                key = f"{lo:.2f}-{hi:.2f}" if hi is not None else f"{lo:.2f}+"
                out[key] = sum(1 for v in values if v is not None and v >= lo and (hi is None or v < hi))
            return out

        by_type = {}
        for t in sorted({a.get("type") for a in answers if a.get("type")}):
            sub = [a for a in answers if a.get("type") == t]
            by_type[t] = {
                "answers": len(sub),
                "delegated": sum(1 for a in sub if a.get("delegate")),
                "delegation_rate": round(sum(1 for a in sub if a.get("delegate")) / len(sub), 4) if sub else None,
                "mean_confidence": round(sum(a["confidence"] for a in sub if a.get("confidence") is not None)
                                         / max(1, len(sub)), 4),
            }
        return {
            "window_hours": hours,
            "requests": len(recs),
            "answers": len(answers),
            "models_seen": dict(Counter(a.get("model") for a in answers if a.get("model"))),
            "answers_delegated": sum(1 for a in answers if a.get("delegate")),
            "delegation_rate": round(sum(1 for a in answers if a.get("delegate")) / len(answers), 4) if answers else None,
            "delegate_kinds": dict(Counter(a.get("delegate_kind") for a in answers if a.get("delegate_kind"))),
            "by_type": by_type,
            "truncated": sum(1 for a in answers if a.get("truncated")),
            "uncalibrated": sum(1 for a in answers if a.get("calibrated") is False),
            "unsupported": sum(1 for a in answers if a.get("supported") is False),
            "latency_ms": {"p50": _pct(lat, 0.50), "p90": _pct(lat, 0.90), "p95": _pct(lat, 0.95),
                           "p99": _pct(lat, 0.99), "max": round(lat[-1], 2) if lat else None},
            "confidence_hist": hist([a.get("confidence") for a in answers],
                                    [0.0, 0.5, 0.6, 0.7, 0.75, 0.9, 0.95, 1.0001]),
            "neutral_mass_hist": hist([a.get("neutral_mass") for a in answers],
                                      [0.0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0001]),
            "chars": {"p50": _pct(sorted(r["request"]["chars"] for r in recs), 0.50),
                      "p95": _pct(sorted(r["request"]["chars"] for r in recs), 0.95)},
            "languages": dict(Counter(r["request"].get("lang_guess") for r in recs)),
            "log": {"written": self._written, "errors": self._errors, "level": self.level,
                    "directory": str(self.directory), "files": len(list(self.directory.glob("decisions-*.jsonl")))
                    if self.directory.exists() else 0},
        }

    # ------------------------------------------------------------------ maintenance
    def prune(self) -> int:
        """Deletes files older than `retain_days`. Returns how many it deleted."""
        if not self.directory.exists() or self.retain_days <= 0:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retain_days)
        removed = 0
        for path in self.directory.glob("decisions-*.jsonl"):
            try:
                stamp = datetime.strptime(path.stem.split("-", 1)[1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if stamp < cutoff:
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
        return removed


def _short_hash(text: str) -> str:
    import hashlib
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:8]


def _lang_guess(text: str) -> str:
    """Coarse language hint, no dependencies: enough to see the traffic mix."""
    t = (text or "").lower()
    if not t.strip():
        return "empty"
    marks = {
        "es": (" que ", " de ", " no ", " el ", " la ", " los ", " las ", " un ", " una ", " y ",
               " por ", " con ", " para ", " me ", " mi ", " es ", " está", "ñ", "ción", " gracias"),
        "de": (" und ", " der ", " die ", " das ", " ich ", " nicht", " ist ", " wir ", " sie ",
               " mit ", " für ", " ein ", " eine ", "ß", "sch"),
        "en": (" the ", " and ", " you ", " is ", " it ", " not ", " this ", " that ", " for ",
               " with ", " have ", " my "),
    }
    score = {k: sum(t.count(m) for m in v) for k, v in marks.items()}
    best = max(score, key=score.get)
    return best if score[best] > 0 else "?"
