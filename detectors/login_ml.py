"""Inference adapter for the explicitly synthetic Isolation Forest baseline."""
import time
from pathlib import Path
import joblib
from detectors.contract import DetectorResult
from detectors.login import analyze_login
from features.login import login_vector

DETECTOR_VERSION = "login-iforest-1.0.0"


class LoginIsolationForestDetector:
    def __init__(self, artifact: str | Path):
        path = Path(artifact)
        if not path.is_file():
            raise FileNotFoundError(f"model artifact not found: {path}")
        bundle = joblib.load(path)
        if not isinstance(bundle, dict) or "pipeline" not in bundle or "registry" not in bundle:
            raise ValueError("invalid model artifact")
        self.pipeline = bundle["pipeline"]
        self.registry = bundle["registry"]

    def analyze(self, event: dict) -> DetectorResult:
        analyze_login(event)  # Apply the same strict schema/input validation.
        start = time.perf_counter()
        row = login_vector(event)
        prediction = int(self.pipeline.predict(row)[0])
        score = float(self.pipeline.decision_function(row)[0])
        anomalous = prediction == -1
        evidence = ([{"type": "model_indicator", "indicator": "isolation_forest_outlier", "value": True}]
                    if anomalous else [])
        return DetectorResult(
            detector="login_anomaly_iforest", detector_version=DETECTOR_VERSION, method="ml",
            classification="anomalous_indicators" if anomalous else "no_model_anomaly",
            confidence=None, confidence_status="not_applicable", evidence=evidence,
            features={"decision_function_score_higher_is_more_normal": score,
                      "feature_version": self.registry["features_version"],
                      "history_available": False},
            limitations=list(self.registry.get("limitations", [])),
            processing_time_ms=(time.perf_counter() - start) * 1000,
            model_version=self.registry["model_version"],
        )
