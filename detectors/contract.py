"""Shared, validated detector output contract."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

Method = Literal["ml", "rule", "heuristic", "hybrid"]


@dataclass
class DetectorResult:
    detector: str
    detector_version: str
    method: Method
    classification: str
    confidence: float | None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    features: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    processing_time_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    model_version: str | None = None
    confidence_status: str = "unavailable"

    def __post_init__(self) -> None:
        if not self.detector or not self.detector_version or not self.classification:
            raise ValueError("detector, detector_version and classification are required")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1 or None")
        if self.processing_time_ms < 0:
            raise ValueError("processing_time_ms cannot be negative")
        if self.confidence is None and self.confidence_status == "measured":
            raise ValueError("measured confidence cannot be null")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
