"""Mechanics-only tests; hand-authored rows below are not an evaluation dataset."""
import pytest


def test_phishing_model_roundtrip_in_tmp_path(tmp_path):
    pytest.importorskip("sklearn")
    import csv
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    import joblib
    from detectors.phishing import PhishingNLPDetector
    rows = [("meeting agenda project update", "benign"), ("team lunch schedule", "benign"),
            ("verify password account login", "phishing"), ("urgent bank payment credentials", "phishing")]
    pipe = Pipeline([("tfidf", TfidfVectorizer()), ("classifier", LogisticRegression())]).fit([r[0] for r in rows], [r[1] for r in rows])
    artifact = tmp_path / "model.joblib"
    joblib.dump({"pipeline": pipe, "registry": {"model_version": "test-only", "features_version": "test", "limitations": ["unit test"]}}, artifact)
    result = PhishingNLPDetector(artifact).analyze("urgent verify password")
    assert {"detector", "detector_version", "method", "classification", "confidence", "evidence",
            "features", "limitations", "processing_time_ms", "timestamp", "model_version",
            "confidence_status"} <= result.to_dict().keys()
    assert result.detector == "phishing_nlp" and result.model_version == "test-only"
    assert result.confidence is None or 0 <= result.confidence <= 1
    assert result.features["feature_version"]
    with pytest.raises(ValueError): PhishingNLPDetector(artifact).analyze("  ")


def test_missing_model_is_actionable(tmp_path):
    pytest.importorskip("sklearn")
    from detectors.phishing import PhishingNLPDetector
    with pytest.raises(FileNotFoundError): PhishingNLPDetector(tmp_path / "missing.joblib")


def test_prepare_dataset_schema_and_label_mapping(tmp_path):
    import csv
    from training.prepare_dataset import prepare_csv
    src, dst = tmp_path / "source.csv", tmp_path / "clean.csv"
    with src.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["body", "category"])
        writer.writeheader()
        for i in range(12):
            writer.writerow({"body": f"positive message {i}", "category": "bad"})
            writer.writerow({"body": f"ordinary note {i}", "category": "good"})
    counts = prepare_csv(src, dst, "body", "category", "bad", "good")
    assert counts["phishing"] == counts["benign"] == 12
    bad = tmp_path / "unmapped.csv"
    with bad.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["body", "category"])
        writer.writeheader()
        for i in range(12):
            writer.writerow({"body": f"positive message {i}", "category": "bad"})
            writer.writerow({"body": f"ordinary note {i}", "category": "unknown"})
    with pytest.raises(ValueError, match="unmapped label"):
        prepare_csv(bad, tmp_path / "invalid.csv", "body", "category", "bad", "good")
