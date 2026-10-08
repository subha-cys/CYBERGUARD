"""Inference adapters for locally trained multimedia feature baselines."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib

from detectors.multimedia import AudioDeepfakeModel, ImageManipulationModel, VideoDeepfakeModel
from training.media import _numeric_features


class _TrainedMediaModel:
    modality: str

    def __init__(self, artifact: str | Path):
        path = Path(artifact)
        if not path.is_file():
            raise FileNotFoundError(f"media model artifact not found: {path}")
        bundle = joblib.load(path)
        if not isinstance(bundle, dict) or not {"pipeline", "registry"} <= bundle.keys():
            raise ValueError("invalid media model artifact")
        registry = bundle["registry"]
        if not isinstance(registry, dict) or registry.get("modality") != self.modality:
            raise ValueError(f"media model artifact is not a {self.modality} model")
        self.pipeline = bundle["pipeline"]
        self.registry = registry
        self.model_version = str(registry.get("model_version", ""))
        self.evaluation_reference = f"held-out dataset sha256:{registry.get('dataset_sha256', '')}"
        self.feature_names = registry.get("feature_names")
        self.threshold = registry.get("threshold")
        if (
            not self.model_version
            or not isinstance(self.feature_names, list)
            or not self.feature_names
            or not isinstance(self.threshold, (int, float))
            or not 0 <= self.threshold <= 1
            or registry.get("probabilities_calibrated") is not False
        ):
            raise ValueError("media model registry is missing required version, feature, threshold, or calibration metadata")

    def analyze(self, path: Path, features: dict[str, Any]) -> dict[str, Any]:
        del path
        _, vector = _numeric_features(features, self.feature_names)
        classes = list(self.pipeline.named_steps["classifier"].classes_)
        if "synthetic" not in classes:
            raise ValueError("media model does not contain the required synthetic class")
        scores = self.pipeline.predict_proba([vector])[0]
        synthetic_score = float(scores[classes.index("synthetic")])
        distance = synthetic_score - float(self.threshold)
        if distance > 0.05:
            label = "synthetic"
            classification = "manipulation_indicators_detected"
        elif distance < -0.05:
            label = "authentic"
            classification = "no_significant_indicators"
        else:
            label = "inconclusive"
            classification = "inconclusive"
        limitations = list(self.registry.get("limitations", []))
        return {
            "classification": classification,
            "confidence": None,
            "evidence": [{
                "indicator": "manipulation_model_indicator",
                "type": "uncalibrated_model_score",
                "value": {
                    "synthetic_class_score_not_probability": round(synthetic_score, 4),
                    "validation_selected_threshold": round(float(self.threshold), 4),
                    "model_assessment": label,
                },
            }],
            "limitations": limitations,
            "voice_origin": (
                {
                    "classification": (
                        "likely_ai_generated" if label == "synthetic"
                        else "likely_human" if label == "authentic"
                        else "inconclusive"
                    ),
                    "method": "group_evaluated_feature_model",
                    "confidence": None,
                    "evidence": ["trained_media_model_score"],
                    "limitations": limitations,
                }
                if self.modality == "audio" else None
            ),
        }


class TrainedImageModel(_TrainedMediaModel, ImageManipulationModel):
    modality = "image"


class TrainedAudioModel(_TrainedMediaModel, AudioDeepfakeModel):
    modality = "audio"


class TrainedVideoModel(_TrainedMediaModel, VideoDeepfakeModel):
    modality = "video"


def load_media_model(modality: str, artifact: str | Path):
    model_types = {
        "image": TrainedImageModel,
        "audio": TrainedAudioModel,
        "video": TrainedVideoModel,
    }
    try:
        model_type = model_types[modality]
    except KeyError as exc:
        raise ValueError("modality must be image, audio, or video") from exc
    return model_type(artifact)
