"""Reproducible comparison and evaluation of TF-IDF linear baselines."""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC
import joblib

LABELS = ["benign", "phishing"]
MODEL_VERSION = "phishing-tfidf-linear-1.0.0"
DATASET_VERSION = "user-supplied-csv-1.0.0"
FEATURE_VERSION = "tfidf-word-1.0.0"


def load_dataset(path: str | Path) -> tuple[list[str], list[str], str]:
    p = Path(path)
    hasher = hashlib.sha256()
    with p.open("rb") as data_handle:
        for chunk in iter(lambda: data_handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    texts, labels = [], []
    csv.field_size_limit(100_000_000)
    with p.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"text", "label"}.issubset(reader.fieldnames):
            raise ValueError("CSV must have text,label columns")
        for line, row in enumerate(reader, 2):
            text, label = (row.get("text") or "").strip(), (row.get("label") or "").strip().lower()
            if not text or label not in LABELS:
                raise ValueError(f"invalid text or label on CSV line {line}; labels are benign/phishing")
            texts.append(text)
            labels.append(label)
    counts = {label: labels.count(label) for label in LABELS}
    if len(texts) < 40 or min(counts.values()) < 10:
        raise ValueError("need at least 40 rows and 10 examples per class for stratified train/validation/test evaluation")
    return texts, labels, digest


def _metrics(y_true, y_pred):
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_macro": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "confusion_matrix_labels": LABELS,
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=LABELS).tolist(),
    }


def train_and_evaluate(csv_path: str | Path, output_dir: str | Path) -> dict:
    texts, labels, data_hash = load_dataset(csv_path)
    # Fixed, stratified split; the test partition is not consulted for model selection.
    x_train, x_hold, y_train, y_hold = train_test_split(texts, labels, test_size=0.30, random_state=42, stratify=labels)
    x_val, x_test, y_val, y_test = train_test_split(x_hold, y_hold, test_size=0.50, random_state=43, stratify=y_hold)
    candidates = {
        "logistic_regression": LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42),
        "linear_svm": LinearSVC(class_weight="balanced", random_state=42),
    }
    validation = {}
    for name, classifier in candidates.items():
        pipeline = Pipeline([("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=50000, sublinear_tf=True)), ("classifier", classifier)])
        pipeline.fit(x_train, y_train)
        validation[name] = _metrics(y_val, pipeline.predict(x_val))
        del pipeline
    selected = max(candidates, key=lambda name: (validation[name]["f1_macro"], name == "logistic_regression"))
    chosen = Pipeline([("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=50000, sublinear_tf=True)),
                       ("classifier", candidates[selected])])
    chosen.fit(x_train, y_train)
    test_metrics = _metrics(y_test, chosen.predict(x_test))
    counts = {label: labels.count(label) for label in LABELS}
    prepared_manifest_path = Path(csv_path).with_suffix(".manifest.json")
    prepared_manifest = json.loads(prepared_manifest_path.read_text(encoding="utf-8")) if prepared_manifest_path.exists() else {}
    source_meta = prepared_manifest.get("source_dataset_manifest", {})
    registry = {
        "model_name": "phishing_email_tfidf",
        "model_version": MODEL_VERSION,
        "dataset": source_meta.get("dataset", str(Path(csv_path).name)),
        "dataset_version": source_meta.get("version", DATASET_VERSION),
        "dataset_source_url": source_meta.get("url"),
        "dataset_license": source_meta.get("license"),
        "source_dataset_file": prepared_manifest.get("source"),
        "source_dataset_md5": prepared_manifest.get("source_md5", source_meta.get("source_md5")),
        "normalized_dataset_sha256": data_hash,
        "features_version": FEATURE_VERSION,
        "preprocessing_version": "utf8-strip-lower-label-no-text-rewrite-1.0.0",
        "training_timestamp": datetime.now(timezone.utc).isoformat(),
        "algorithm": selected,
        "candidate_validation_metrics": validation,
        "test_metrics": test_metrics,
        "class_counts": counts,
        "class_imbalance_ratio_major_to_minor": max(counts.values()) / min(counts.values()),
        "split_counts": {"train": len(y_train), "validation": len(y_val), "test": len(y_test)},
        "limitations": ["Metrics describe this corpus and random stratified split only.", "External and temporal generalization is unmeasured.",
                         "The selected Linear SVM has no calibrated confidence output." if selected == "linear_svm" else "Logistic Regression probabilities are not calibrated."],
        "random_seeds": {"train_test_split": 42, "validation_test_split": 43, "model": 42},
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": chosen, "registry": registry}, out / "model.joblib")
    (out / "registry.json").write_text(json.dumps(registry, indent=2), encoding="utf-8")
    return registry


def refresh_existing_registry(model_path: str | Path, csv_path: str | Path) -> dict:
    """Attach dataset provenance to an existing model without changing model weights."""
    path = Path(model_path)
    bundle = joblib.load(path)
    prepared_path = Path(csv_path).with_suffix(".manifest.json")
    if not prepared_path.is_file():
        raise ValueError("prepared dataset manifest is required")
    prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
    source = prepared.get("source_dataset_manifest", {})
    registry = bundle.get("registry", {})
    registry.update({
        "dataset": source.get("dataset", registry.get("dataset")),
        "dataset_version": source.get("version", DATASET_VERSION),
        "dataset_source_url": source.get("url"),
        "dataset_license": source.get("license"),
        "source_dataset_file": prepared.get("source"),
        "source_dataset_md5": prepared.get("source_md5"),
        "normalized_dataset_sha256": prepared.get("rows", {}).get("normalized_sha256"),
        "features_version": FEATURE_VERSION,
        "limitations": ["Metrics describe this corpus and random stratified split only.",
                        "External and temporal generalization is unmeasured.",
                        "The selected Linear SVM has no calibrated confidence output." if registry.get("algorithm") == "linear_svm" else "Logistic Regression probabilities are not calibrated."],
    })
    registry.pop("dataset_sha256", None)
    bundle["registry"] = registry
    joblib.dump(bundle, path)
    path.with_name("registry.json").write_text(json.dumps(registry, indent=2), encoding="utf-8")
    return registry
