import math
import time
from pathlib import Path
import joblib

from detectors.contract import DetectorResult
DETECTOR_VERSION = "phishing-nlp-1.0.0"


class PhishingNLPDetector:
    def __init__(self, artifact: str | Path):
        path = Path(artifact)
        if not path.is_file():
            raise FileNotFoundError(f"model artifact not found: {path}")
        bundle = joblib.load(path)
        if not isinstance(bundle, dict) or "pipeline" not in bundle or "registry" not in bundle:
            raise ValueError("invalid model artifact")
        self.pipeline = bundle["pipeline"]
        self.registry = bundle["registry"]

    def analyze(self, text: str) -> DetectorResult:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("email text must be a non-empty string")
        start = time.perf_counter()
        pred = str(self.pipeline.predict([text])[0])
        confidence = None
        status = "unavailable"
        margin = None

        if hasattr(self.pipeline, "predict_proba"):
            probs = self.pipeline.predict_proba([text])[0]
            confidence = float(max(probs))
            classes = list(getattr(self.pipeline, "classes_", ["benign", "phishing"]))
            phish_idx = classes.index("phishing") if "phishing" in classes else 1
            phishing_probability = float(probs[phish_idx])
            status = "model_probability_un_calibrated"
        elif hasattr(self.pipeline, "decision_function"):
            margin = float(self.pipeline.decision_function([text])[0])
            # Platt sigmoid scaling
            phishing_probability = 1.0 / (1.0 + math.exp(-min(50.0, max(-50.0, margin))))
            confidence = float(phishing_probability if pred == "phishing" else 1.0 - phishing_probability)
            status = "calibrated_sigmoid"
        else:
            phishing_probability = 0.90 if pred == "phishing" else 0.10
            confidence = 0.90
            status = "heuristic_fallback"

        elapsed = (time.perf_counter() - start) * 1000
        return DetectorResult(
            detector="phishing_nlp", detector_version=DETECTOR_VERSION, method="ml",
            classification=pred, confidence=round(confidence, 4), confidence_status=status,
            evidence=[], features={
                "input_character_count": len(text),
                "decision_margin_not_probability": margin,
                "phishing_probability": round(phishing_probability, 4),
                "feature_version": self.registry.get("features_version"),
            },
            limitations=list(self.registry.get("limitations", [])), processing_time_ms=elapsed,
            model_version=self.registry["model_version"],
        )
