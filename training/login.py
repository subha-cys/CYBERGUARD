"""Isolation Forest baseline evaluated against generated synthetic labels."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import joblib
from sklearn.ensemble import IsolationForest
from sklearn.metrics import confusion_matrix, precision_score, recall_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from datasets.login_synthetic import generate_login_events
from features.login import login_vector, LOGIN_FEATURE_VERSION


def _matrix(rows):
    return [login_vector(event)[0] for event in rows]


def datetime_hour(value):
    from datetime import datetime
    return datetime.fromisoformat(value.replace("Z", "+00:00")).hour


def evaluate_isolation_forest(n: int = 1000, seed: int = 17, output_dir: str | Path = "models/login") -> dict:
    rows = generate_login_events(n, seed)
    labels = [int(r["ground_truth_anomaly"]) for r in rows]
    x_train, x_test, y_train, y_test = train_test_split(_matrix(rows), labels,
                                                    test_size=0.30, random_state=41,
                                                    stratify=labels)
   
    normal_train = [x for x, y in zip(x_train, y_train) if y == 0]


    model = Pipeline([("scale", StandardScaler()), ("iforest", IsolationForest(n_estimators=200, contamination=0.20, random_state=seed))])
    model.fit(normal_train)
    pred = (model.predict(x_test) == -1).astype(int)
    metrics = {
        "dataset": "seeded-synthetic-login-v1",
        "generation": "20% anomalous events: UTC hour 00-04, 5-9 failed attempts, random success; normal events: hour 07-20, 0-2 failures, successful; IP/device are synthetic documentation-space values.",
        "seed": seed, "n": n,
        "algorithm": "IsolationForest(contamination=0.20)",
        "metrics": {"precision": float(precision_score(y_test, pred, zero_division=0)),
                    "recall": float(recall_score(y_test, pred, zero_division=0)),
                    "f1": float(f1_score(y_test, pred, zero_division=0)),
                    "confusion_matrix_labels": ["normal", "anomaly"],
                    "confusion_matrix": confusion_matrix(y_test, pred, labels=[0, 1]).tolist()},
        "limitations": ["Metrics measure recovery of deliberately separable synthetic patterns only.", "Not evidence of real-world account takeover performance."],
    }
    dataset_hash = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    registry = {
        "model_name": "login_anomaly_isolation_forest",
        "model_version": "login-iforest-synthetic-1.0.0",
        "dataset": "seeded-synthetic-login-v1", "dataset_version": "synthetic-generator-1.0.0",
        "dataset_sha256": dataset_hash, "features_version": LOGIN_FEATURE_VERSION,
        "training_timestamp": datetime.now(timezone.utc).isoformat(),
        "algorithm": "IsolationForest(contamination=0.20)", "metrics": metrics["metrics"],
        "limitations": metrics["limitations"], "seed": seed,
    }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": model, "registry": registry}, out / "model.joblib")
    (out / "registry.json").write_text(json.dumps(registry, indent=2), encoding="utf-8")
    metrics["model_version"] = registry["model_version"]
    return metrics
