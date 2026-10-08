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
    assert result.confidence is None
    assert result.features["phishing_probability"] is None
    assert result.features["phishing_model_score_uncalibrated"] is not None
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


def test_media_training_keeps_source_groups_disjoint_and_loads_audio_adapter(tmp_path, monkeypatch):
    import csv
    from detectors.media_model import load_media_model
    from training import media

    manifest = tmp_path / "audio_manifest.csv"
    rows = []
    for group_index in range(12):
        for label in ("authentic", "synthetic"):
            for sample_index in range(4):
                name = f"group{group_index:02d}_{label}_{sample_index}.wav"
                (tmp_path / name).write_bytes(f"{group_index}:{label}:{sample_index}".encode())
                rows.append({"file": name, "label": label, "group_id": f"group{group_index:02d}"})

    with manifest.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["file", "label", "group_id"])
        writer.writeheader()
        writer.writerows(rows)

    def fake_features(modality, path):
        assert modality == "audio"
        return {
            "class_cue": float("_synthetic_" in path.name),
            "source_variation": float(path.name[5:7]),
        }

    monkeypatch.setattr(media, "_features_for", fake_features)
    registry = media.train_and_evaluate("audio", manifest, tmp_path / "models", seed=13)

    assert registry["group_leakage_check_passed"] is True
    assert set(registry["held_out_test_metrics"]["confusion_matrix_labels"]) == {"authentic", "synthetic"}
    assert "false_positive_rate" in registry["held_out_test_metrics"]
    adapter = load_media_model("audio", tmp_path / "models" / "audio.joblib")
    output = adapter.analyze(
        tmp_path / "group00_synthetic_00.wav",
        {"class_cue": 1.0, "source_variation": 0.0},
    )
    assert output["classification"] == "manipulation_indicators_detected"
    assert output["confidence"] is None
    assert output["voice_origin"]["classification"] == "likely_ai_generated"
