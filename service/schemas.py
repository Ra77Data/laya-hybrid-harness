"""Contrato HTTP del servicio. Compatible con el plugin de DSH: solo se agregan campos."""
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
    # Fija el modelo para todas las preguntas, saltando el enrutamiento. Sirve para comparar
    # modelos con la misma batería sin tocar la config ni reiniciar el servicio.
    model: str | None = None


class Answer(BaseModel):
    id: str
    type: str
    value: object = None
    model_used: str | None = None         # qué modelo contestó esta pregunta
    confidence: float = 0.0
    raw_confidence: float | None = None
    calibrated: bool = False
    temperature: float | None = None      # la T realmente aplicada, no "hay archivo"
    calibration_note: str | None = None   # por qué NO se calibró, cuando no se pudo
    probs: list[float] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)
    delegate_to_cloud: bool = False
    delegate_reason: str | None = None
    threshold: float | None = None        # umbral aplicado a esta primitiva
    supported: bool = True                # false si el modelo no sabe responder ese tipo
    neutral_mass: float | None = None     # P(neutro) cuando el modelo la calcula
    truncated: bool = False               # el modelo no vio el texto completo
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
    models: dict = Field(default_factory=dict)   # estado por modelo: cargado, pesos, self-test
