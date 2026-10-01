"""HTTP contract of the service. Compatible with the DSH plugin: fields are only ever added."""
from pydantic import BaseModel, Field


class Question(BaseModel):
    id: str
    type: str = Field(pattern=r"^(noul|choice|score)$")
    instructions: str = ""
    options: list[str] = Field(default_factory=list)
    scale: list[str] = Field(default_factory=list)


class DecideRequest(BaseModel):
    state: str
    questions: list[Question]
    # Pins the model for every question, skipping routing. Useful to compare models
    # on the same battery without touching the config or restarting the service.
    model: str | None = None


class Answer(BaseModel):
    id: str
    type: str
    value: object = None
    model_used: str | None = None         # which model answered this question
    confidence: float = 0.0
    raw_confidence: float | None = None
    calibrated: bool = False
    temperature: float | None = None      # the T actually applied, not "a file exists"
    calibration_note: str | None = None   # why it was NOT calibrated, when it could not be
    probs: list[float] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)
    delegate_to_cloud: bool = False
    delegate_reason: str | None = None
    threshold: float | None = None        # threshold applied to this primitive
    supported: bool = True                # false if the model cannot answer that type
    neutral_mass: float | None = None     # P(neutral) when the model computes it
    truncated: bool = False               # the model did not see the whole text
    input_tokens: int | None = None
    max_length: int | None = None


class DecideResponse(BaseModel):
    model: str
    adapter: str = ""
    calibration_version: int = 0
    latency_ms: float = 0.0
    answers: list[Answer]


class HealthResponse(BaseModel):
    status: str
    model: str
    label: str = ""
    adapter: str = ""
    supports: list[str] = Field(default_factory=list)
    weights: dict = Field(default_factory=dict)
    calibration: dict = Field(default_factory=dict)
    delegation: dict = Field(default_factory=dict)
    smoke_ok: bool | None = None
    routing: dict = Field(default_factory=dict)
    models: dict = Field(default_factory=dict)   # per-model state: loaded, weights, self-test
    lifecycle: dict = Field(default_factory=dict)  # idle-unload policy and what is loaded right now
