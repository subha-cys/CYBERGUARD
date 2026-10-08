"""Group-aware training and evaluation for local image, audio, and video baselines."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

LABELS = ("authentic", "synthetic")
LABEL_MAP = {
    "real": "authentic",
    "human": "authentic",
    "authentic": "authentic",
    "ai_generated": "synthetic",
    "synthetic": "synthetic",
}
FEATURE_VERSION = "multimedia-numeric-features-1.1.0"
MAX_MEDIA_BYTES = 100 * 1024 * 1024


def _features_for(modality: str, path: Path) -> dict[str, Any]:
    if modality == "image":
        from features.multimedia_image import extract_image_features

        return extract_image_features(path)
    if modality == "audio":
        from features.multimedia_audio import extract_audio_features

        return extract_audio_features(path)
    if modality == "video":
        from features.multimedia_video import extract_video_features

        return extract_video_features(path)
    raise ValueError("modality must be image, audio, or video")


def _numeric_features(features: dict[str, Any], feature_names: list[str] | None = None) -> tuple[list[str], list[float]]:
    values: dict[str, float] = {}
    for name, value in features.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        numeric = float(value)
        if math.isfinite(numeric):
            values[name] = numeric
    names = feature_names if feature_names is not None else sorted(values)
    if not names:
        raise ValueError("feature extraction produced no finite numeric features")
    missing = [name for name in names if name not in values]
    if missing:
        raise ValueError(f"feature schema mismatch; missing numeric features: {', '.join(missing)}")
    return names, [values[name] for name in names]


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(path: str | Path, modality: str) -> tuple[list[list[float]], list[str], list[str], list[str], str]:
    manifest = Path(path).resolve()
    if not manifest.is_file():
        raise FileNotFoundError(f"training manifest not found: {manifest}")

    rows: list[list[float]] = []
    labels: list[str] = []
    groups: list[str] = []
    names: list[str] | None = None
    digest = hashlib.sha256()
    seen_content: dict[str, str] = {}
    with manifest.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"file", "label", "group_id"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("manifest CSV must contain file,label,group_id columns")
        for line_number, row in enumerate(reader, 2):
            relative_path = (row.get("file") or "").strip()
            raw_label = (row.get("label") or "").strip().casefold().replace("-", "_").replace(" ", "_")
            group = (row.get("group_id") or "").strip()
            label = LABEL_MAP.get(raw_label)
            if not relative_path or not group or label not in LABELS:
                raise ValueError(f"manifest line {line_number} requires file, group_id, and authentic/synthetic label")
            media_path = (manifest.parent / relative_path).resolve()
            if not media_path.is_relative_to(manifest.parent.resolve()):
                raise ValueError(f"manifest line {line_number} file must remain under the manifest directory")
            if not media_path.is_file():
                raise FileNotFoundError(f"training media not found on manifest line {line_number}: {relative_path}")
            size = media_path.stat().st_size
            if not 0 < size <= MAX_MEDIA_BYTES:
                raise ValueError(f"training media on line {line_number} must be between 1 byte and {MAX_MEDIA_BYTES} bytes")
            file_hash = _hash_file(media_path)
            previous_group = seen_content.get(file_hash)
            if previous_group is not None and previous_group != group:
                raise ValueError(f"identical media occurs in different groups on manifest line {line_number}")
            if previous_group is not None:
                raise ValueError(f"duplicate media entry on manifest line {line_number}")
            seen_content[file_hash] = group
            try:
                extracted = _features_for(modality, media_path)
                current_names, vector = _numeric_features(extracted, names)
            except Exception as exc:
                raise ValueError(f"could not extract {modality} features on manifest line {line_number}: {exc}") from exc
            names = current_names
            rows.append(vector)
            labels.append(label)
            groups.append(group)
            digest.update(f"{relative_path}\0{label}\0{group}\0{file_hash}\n".encode("utf-8"))

    counts = Counter(labels)
    if len(rows) < 40 or min((counts[label] for label in LABELS), default=0) < 20:
        raise ValueError("need at least 40 media files and 20 examples per class for group-separated evaluation")
    if len(set(groups)) < 8:
        raise ValueError("need at least 8 distinct group_id values to evaluate group generalization")
    return rows, labels, groups, names or [], digest.hexdigest()


def _group_splits(labels: list[str], groups: list[str], seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    indices = np.arange(len(labels))
    y = np.asarray(labels)
    group_array = np.asarray(groups)
    label_set = set(LABELS)
    for attempt in range(100):
        test_splitter = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=seed + attempt)
        train_validation, test = next(test_splitter.split(indices, y, group_array))
        validation_splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=seed + 100 + attempt)
        train_local, validation_local = next(
            validation_splitter.split(train_validation, y[train_validation], group_array[train_validation])
        )
        train = train_validation[train_local]
        validation = train_validation[validation_local]
        if all(set(y[part]) == label_set for part in (train, validation, test)):
            if min(Counter(y[test]).values()) >= 2 and min(Counter(y[validation]).values()) >= 2:
                if not (set(group_array[train]) & set(group_array[validation])
                        or set(group_array[train]) & set(group_array[test])
                        or set(group_array[validation]) & set(group_array[test])):
                    return train, validation, test
    raise ValueError(
        "could not form train/validation/test splits containing both classes without group leakage; "
        "add more distinct source groups per class"
    )


def _metrics(y_true: np.ndarray, scores: np.ndarray, threshold: float) -> dict[str, Any]:
    predicted = np.where(scores >= threshold, "synthetic", "authentic")
    matrix = confusion_matrix(y_true, predicted, labels=LABELS)
    true_negative, false_positive, false_negative, true_positive = matrix.ravel()
    return {
        "threshold": round(float(threshold), 4),
        "precision_synthetic": float(precision_score(y_true, predicted, pos_label="synthetic", zero_division=0)),
        "recall_synthetic": float(recall_score(y_true, predicted, pos_label="synthetic", zero_division=0)),
        "f1_synthetic": float(f1_score(y_true, predicted, pos_label="synthetic", zero_division=0)),
        "false_positive_rate": float(false_positive / max(1, false_positive + true_negative)),
        "false_negative_rate": float(false_negative / max(1, false_negative + true_positive)),
        "confusion_matrix_labels": list(LABELS),
        "confusion_matrix": matrix.tolist(),
        "sample_count": int(len(y_true)),
    }


def train_and_evaluate(
    modality: str,
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    seed: int = 42,
) -> dict[str, Any]:
    """Train one modality model and report held-out group metrics."""
    if modality not in {"image", "audio", "video"}:
        raise ValueError("modality must be image, audio, or video")
    x_rows, labels, groups, feature_names, dataset_hash = _load_manifest(manifest_path, modality)
    x = np.asarray(x_rows, dtype=np.float64)
    y = np.asarray(labels)
    train, validation, test = _group_splits(labels, groups, seed)

    pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("classifier", LogisticRegression(max_iter=2000, class_weight="balanced", random_state=seed)),
    ])
    pipeline.fit(x[train], y[train])
    classes = list(pipeline.named_steps["classifier"].classes_)
    synthetic_index = classes.index("synthetic")
    validation_scores = pipeline.predict_proba(x[validation])[:, synthetic_index]
    thresholds = np.linspace(0.05, 0.95, 91)
    threshold = max(
        thresholds,
        key=lambda candidate: (
            f1_score(y[validation], np.where(validation_scores >= candidate, "synthetic", "authentic"),
                     pos_label="synthetic", zero_division=0),
            precision_score(y[validation], np.where(validation_scores >= candidate, "synthetic", "authentic"),
                            pos_label="synthetic", zero_division=0),
            -candidate,
        ),
    )
    test_scores = pipeline.predict_proba(x[test])[:, synthetic_index]
    test_metrics = _metrics(y[test], test_scores, float(threshold))
    group_sets = {
        "train": set(np.asarray(groups)[train]),
        "validation": set(np.asarray(groups)[validation]),
        "test": set(np.asarray(groups)[test]),
    }
    registry = {
        "model_name": f"{modality}_authenticity_baseline",
        "model_version": f"{modality}-logistic-features-1.0.0",
        "modality": modality,
        "feature_version": FEATURE_VERSION,
        "feature_names": feature_names,
        "dataset_sha256": dataset_hash,
        "label_mapping": LABEL_MAP,
        "training_timestamp": datetime.now(timezone.utc).isoformat(),
        "algorithm": "median imputation, standard scaling, class-balanced logistic regression",
        "threshold_selection": "maximum synthetic-class F1 on a group-separated validation partition",
        "threshold": float(threshold),
        "validation_metrics_at_threshold": _metrics(y[validation], validation_scores, float(threshold)),
        "held_out_test_metrics": test_metrics,
        "class_counts": dict(Counter(labels)),
        "split_group_counts": {name: len(values) for name, values in group_sets.items()},
        "group_leakage_check_passed": not (
            group_sets["train"] & group_sets["validation"]
            or group_sets["train"] & group_sets["test"]
            or group_sets["validation"] & group_sets["test"]
        ),
        "probabilities_calibrated": False,
        "limitations": [
            "This model is a feature-based baseline, not a universal deepfake detector.",
            "Model scores are uncalibrated and are not probabilities or confidence.",
            "Held-out metrics describe only the submitted dataset and split; external generalization is unmeasured.",
            "Only generated-versus-authentic labels are accepted; edited content needs a separately defined target and label policy.",
        ],
        "random_seed": seed,
    }

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    artifact = destination / f"{modality}.joblib"
    registry_path = destination / f"{modality}.registry.json"
    temp_artifact: Path | None = None
    temp_registry: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{modality}-", suffix=".joblib", dir=destination, delete=False) as f:
            temp_artifact = Path(f.name)
        joblib.dump({"pipeline": pipeline, "registry": registry}, temp_artifact)
        with tempfile.NamedTemporaryFile(prefix=f".{modality}-", suffix=".json", mode="w",
                                         encoding="utf-8", dir=destination, delete=False) as f:
            temp_registry = Path(f.name)
            json.dump(registry, f, indent=2)
            f.write("\n")
        temp_artifact.replace(artifact)
        temp_registry.replace(registry_path)
    finally:
        if temp_artifact is not None:
            temp_artifact.unlink(missing_ok=True)
        if temp_registry is not None:
            temp_registry.unlink(missing_ok=True)
    return registry


def train_reviewed_features(
    modality: str,
    examples: list[dict[str, Any]],
    output_dir: str | Path,
    *,
    seed: int = 42,
) -> dict[str, Any]:
    """Retrain from confirmed local memory and promote only on held-out improvement."""
    if modality not in {"image", "audio", "video"}:
        raise ValueError("modality must be image, audio, or video")
    if not examples:
        raise ValueError("there are no human-reviewed learning examples")

    rows: list[list[float]] = []
    labels: list[str] = []
    groups: list[str] = []
    predictions: list[str] = []
    feature_names: list[str] | None = None
    digest = hashlib.sha256()
    for example in examples:
        if example.get("feature_version") != FEATURE_VERSION:
            raise ValueError("learning memory uses a different feature version; clear it and collect fresh examples")
        label = example.get("label")
        group = example.get("group_id")
        prediction = example.get("original_prediction")
        if label not in LABELS or not isinstance(group, str) or not group.strip():
            raise ValueError("each reviewed example needs an authentic/synthetic label and source group")
        if prediction not in LABELS:
            raise ValueError("learning memory contains an unsupported original prediction")
        current_names, vector = _numeric_features(example.get("features", {}), feature_names)
        if feature_names is not None and current_names != feature_names:
            raise ValueError("reviewed examples have mismatched numeric feature schemas")
        feature_names = current_names
        rows.append(vector)
        labels.append(label)
        groups.append(group)
        predictions.append(prediction)
        digest.update(
            json.dumps(
                [example.get("sample_id"), label, group, current_names, vector],
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        )

    counts = Counter(labels)
    if len(rows) < 40 or min((counts[label] for label in LABELS), default=0) < 20:
        return {
            "promoted": False,
            "status": "collecting",
            "message": "Training needs 40 reviewed examples, with at least 20 per label.",
            "reviewed_count": len(rows),
            "class_counts": dict(counts),
        }
    if len(set(groups)) < 8:
        return {
            "promoted": False,
            "status": "collecting",
            "message": "Training needs at least 8 distinct source groups.",
            "reviewed_count": len(rows),
            "class_counts": dict(counts),
            "source_group_count": len(set(groups)),
        }

    x = np.asarray(rows, dtype=np.float64)
    y = np.asarray(labels)
    train, validation, test = _group_splits(labels, groups, seed)
    pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("classifier", LogisticRegression(max_iter=2000, class_weight="balanced", random_state=seed)),
    ])
    pipeline.fit(x[train], y[train])
    classes = list(pipeline.named_steps["classifier"].classes_)
    synthetic_index = classes.index("synthetic")
    validation_scores = pipeline.predict_proba(x[validation])[:, synthetic_index]
    thresholds = np.linspace(0.05, 0.95, 91)
    threshold = max(
        thresholds,
        key=lambda candidate: (
            f1_score(
                y[validation],
                np.where(validation_scores >= candidate, "synthetic", "authentic"),
                pos_label="synthetic",
                zero_division=0,
            ),
            precision_score(
                y[validation],
                np.where(validation_scores >= candidate, "synthetic", "authentic"),
                pos_label="synthetic",
                zero_division=0,
            ),
            -candidate,
        ),
    )
    test_scores = pipeline.predict_proba(x[test])[:, synthetic_index]
    test_metrics = _metrics(y[test], test_scores, float(threshold))
    baseline_scores = np.asarray(
        [1.0 if predictions[index] == "synthetic" else 0.0 for index in test],
        dtype=np.float64,
    )
    baseline_metrics = _metrics(y[test], baseline_scores, 0.5)
    group_sets = {
        "train": set(np.asarray(groups)[train]),
        "validation": set(np.asarray(groups)[validation]),
        "test": set(np.asarray(groups)[test]),
    }
    promoted = (
        test_metrics["f1_synthetic"] > baseline_metrics["f1_synthetic"]
        and test_metrics["false_positive_rate"] <= baseline_metrics["false_positive_rate"]
    )
    registry = {
        "model_name": f"{modality}_reviewed_memory_baseline",
        "model_version": f"{modality}-reviewed-memory-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "modality": modality,
        "feature_version": FEATURE_VERSION,
        "feature_names": feature_names,
        "dataset_sha256": digest.hexdigest(),
        "label_mapping": LABEL_MAP,
        "training_timestamp": datetime.now(timezone.utc).isoformat(),
        "algorithm": "median imputation, standard scaling, class-balanced logistic regression",
        "training_source": "locally reviewed feature-only analysis memory",
        "threshold_selection": "maximum synthetic-class F1 on a group-separated validation partition",
        "threshold": float(threshold),
        "validation_metrics_at_threshold": _metrics(y[validation], validation_scores, float(threshold)),
        "held_out_test_metrics": test_metrics,
        "previous_assessment_test_metrics": baseline_metrics,
        "promotion_gate": (
            "held-out F1 must improve over the saved original assessment and false-positive rate must not increase"
        ),
        "promoted": promoted,
        "class_counts": dict(counts),
        "split_group_counts": {name: len(values) for name, values in group_sets.items()},
        "group_leakage_check_passed": not (
            group_sets["train"] & group_sets["validation"]
            or group_sets["train"] & group_sets["test"]
            or group_sets["validation"] & group_sets["test"]
        ),
        "probabilities_calibrated": False,
        "limitations": [
            "This is a feature-based baseline, not a universal deepfake detector.",
            "Model scores are uncalibrated and are not probabilities or confidence.",
            "Held-out metrics describe only reviewed local examples and do not establish external generalization.",
            "Each promoted candidate improved on the saved original assessments in its group-separated test split; this is not a guarantee of future performance.",
        ],
        "random_seed": seed,
    }
    if promoted:
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        artifact = destination / f"{modality}.joblib"
        registry_path = destination / f"{modality}.registry.json"
        temp_artifact: Path | None = None
        temp_registry: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=f".{modality}-memory-", suffix=".joblib", dir=destination, delete=False
            ) as stream:
                temp_artifact = Path(stream.name)
            joblib.dump({"pipeline": pipeline, "registry": registry}, temp_artifact)
            with tempfile.NamedTemporaryFile(
                prefix=f".{modality}-memory-",
                suffix=".json",
                mode="w",
                encoding="utf-8",
                dir=destination,
                delete=False,
            ) as stream:
                temp_registry = Path(stream.name)
                json.dump(registry, stream, indent=2)
                stream.write("\n")
            temp_artifact.replace(artifact)
            temp_registry.replace(registry_path)
        finally:
            if temp_artifact is not None:
                temp_artifact.unlink(missing_ok=True)
            if temp_registry is not None:
                temp_registry.unlink(missing_ok=True)
    return {
        "promoted": promoted,
        "status": "promoted" if promoted else "not_improved",
        "message": (
            "Reviewed model promoted after improving held-out F1 without increasing false positives."
            if promoted
            else "Candidate did not improve held-out F1 while keeping false positives at or below the previous assessment; the active model was left unchanged."
        ),
        "registry": registry,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modality", choices=("image", "audio", "video"), required=True)
    parser.add_argument("--manifest", required=True, help="CSV with file,label,group_id columns")
    parser.add_argument("--output-dir", default="models/media")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    report = train_and_evaluate(args.modality, args.manifest, args.output_dir, seed=args.seed)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
