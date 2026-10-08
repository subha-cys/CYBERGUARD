import time
from pathlib import Path
import joblib

from detectors.contract import DetectorResult
DETECTOR_VERSION = "phishing-nlp-1.1.0"


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
        phishing_score = None
        margin = None

        if hasattr(self.pipeline, "predict_proba"):
            probs = self.pipeline.predict_proba([text])[0]
            classes = list(getattr(self.pipeline, "classes_", []))
            if "phishing" not in classes:
                raise ValueError("phishing model artifact does not contain a phishing class")
            phishing_score = float(probs[classes.index("phishing")])
        elif hasattr(self.pipeline, "decision_function"):
            margin = float(self.pipeline.decision_function([text])[0])

        elapsed = (time.perf_counter() - start) * 1000
        return DetectorResult(
            detector="phishing_nlp", detector_version=DETECTOR_VERSION, method="ml",
            classification=pred, confidence=None, confidence_status="unavailable",
            evidence=[], features={
                "input_character_count": len(text),
                "decision_margin_not_probability": margin,
                "phishing_probability": None,
                "phishing_model_score_uncalibrated": (
                    round(phishing_score, 4) if phishing_score is not None else None
                ),
                "feature_version": self.registry.get("features_version"),
            },
            limitations=list(self.registry.get("limitations", [])), processing_time_ms=elapsed,
            model_version=self.registry["model_version"],
        )
