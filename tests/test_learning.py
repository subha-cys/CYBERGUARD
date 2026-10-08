import json
import sqlite3

import pytest

from backend import learning, service
from training import media


def test_memory_stores_numeric_features_only_and_requires_review(tmp_path):
    database = tmp_path / "learning.sqlite3"
    sample_id = learning.save_pending_example(
        database,
        "audio",
        {
            "vocal_jitter": 0.003,
            "duration_seconds": 5,
            "confidence": 0.99,
            "voice_origin": {"classification": "likely_human"},
            "caption": "private content",
            "analysis_truncated": True,
        },
        "authentic",
    )

    assert sample_id
    with sqlite3.connect(database) as db:
        stored = db.execute(
            "SELECT features_json, confirmed_label, group_id FROM learning_examples WHERE sample_id = ?",
            (sample_id,),
        ).fetchone()
    assert json.loads(stored[0]) == {"duration_seconds": 5.0, "vocal_jitter": 0.003}
    assert stored[1:] == (None, None)
    assert learning.learning_summary(database)["examples"]["audio"]["pending"] == 1


def test_review_requires_pseudonymous_source_group(tmp_path):
    database = tmp_path / "learning.sqlite3"
    sample_id = learning.save_pending_example(
        database, "image", {"ela_mean_error": 2.0}, "authentic"
    )
    with pytest.raises(ValueError, match="group_id"):
        learning.review_example(database, sample_id, "authentic", None)

    reviewed = learning.review_example(database, sample_id, "synthetic", "source-set-01")
    assert reviewed["confirmed_label"] == "synthetic"
    assert reviewed["group_id"] == "source-set-01"
    examples = learning.reviewed_examples(database, "image")
    assert len(examples) == 1
    assert examples[0]["label"] == "synthetic"
    with pytest.raises(ValueError, match="already reviewed"):
        learning.review_example(database, sample_id, "authentic", "source-set-01")


def test_reviewed_examples_are_group_split_and_promoted_only_after_improvement(tmp_path):
    examples = []
    for group_index in range(12):
        for label in ("authentic", "synthetic"):
            for sample_index in range(2):
                examples.append({
                    "sample_id": f"{group_index}-{label}-{sample_index}",
                    "feature_version": media.FEATURE_VERSION,
                    "features": {
                        "class_cue": float(label == "synthetic"),
                        "source_variation": float(group_index),
                    },
                    "label": label,
                    "group_id": f"source-{group_index}",
                    "original_prediction": "authentic" if label == "synthetic" else "synthetic",
                })

    report = media.train_reviewed_features("audio", examples, tmp_path / "models", seed=13)

    assert report["promoted"] is True
    assert report["registry"]["group_leakage_check_passed"] is True
    assert report["registry"]["held_out_test_metrics"]["f1_synthetic"] == 1.0
    assert report["registry"]["previous_assessment_test_metrics"]["f1_synthetic"] == 0.0
    assert (tmp_path / "models" / "audio.joblib").is_file()


def test_analysis_saves_media_features_locally_but_not_demo_or_raw_input(tmp_path, monkeypatch):
    from datasets.media_fixtures import create_normal_image_fixture

    monkeypatch.setattr(service, "DASHBOARD_DB", tmp_path / "dashboard.sqlite3")
    monkeypatch.setattr(service, "DEFAULT_DB", tmp_path / "incidents.sqlite3")
    monkeypatch.setattr(service, "LEARNING_DB", tmp_path / "learning.sqlite3")
    image_path = create_normal_image_fixture()

    result = service.analyze_request({"type": "image", "path": str(image_path)})
    assert result["learning"]["status"] == "awaiting_review"
    assert result["learning"]["raw_content_stored"] is False
    assert learning.learning_summary(service.LEARNING_DB)["examples"]["image"]["pending"] == 1

    demo_result = service.analyze_request(
        {"type": "image", "path": str(image_path), "synthetic_demo": True},
        persist_incident=False,
    )
    assert "learning" not in demo_result
    assert learning.learning_summary(service.LEARNING_DB)["examples"]["image"]["total"] == 1


def test_review_auto_training_waits_for_minimum_data(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "LEARNING_DB", tmp_path / "learning.sqlite3")
    monkeypatch.setattr(service, "MEDIA_MODEL_DIR", tmp_path / "models")
    sample_id = learning.save_pending_example(
        service.LEARNING_DB, "audio", {"vocal_jitter": 0.003}, "authentic"
    )

    result = service.review_learning_sample(sample_id, "authentic", "speaker-01")

    assert result["training"]["status"] == "collecting"
    assert result["training"]["promoted"] is False
    assert result["memory"]["examples"]["audio"]["authentic"] == 1
    assert not (tmp_path / "models" / "audio.joblib").exists()


def test_learning_http_routes_review_and_clear_local_examples(tmp_path, monkeypatch):
    import threading
    from http.server import ThreadingHTTPServer
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen

    from backend import web

    monkeypatch.setattr(service, "LEARNING_DB", tmp_path / "learning.sqlite3")
    monkeypatch.setattr(service, "MEDIA_MODEL_DIR", tmp_path / "models")
    sample_id = learning.save_pending_example(
        service.LEARNING_DB, "audio", {"vocal_jitter": 0.003}, "authentic"
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(f"{base_url}/api/learning") as response:
            assert response.status == 200
            assert json.loads(response.read())["examples"]["audio"]["pending"] == 1

        payload = json.dumps({"label": "authentic", "group_id": "speaker-01"}).encode()
        request = Request(
            f"{base_url}/api/learning/{sample_id}/label",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="PATCH",
        )
        with urlopen(request) as response:
            body = json.loads(response.read())
            assert response.status == 200
            assert body["reviewed"]["confirmed_label"] == "authentic"
            assert body["training"]["status"] == "collecting"

        request = Request(f"{base_url}/api/learning", method="DELETE")
        with urlopen(request) as response:
            body = json.loads(response.read())
            assert response.status == 200
            assert body["examples"]["audio"]["total"] == 0

        request = Request(
            f"{base_url}/api/learning/{sample_id}/label",
            data=json.dumps({"label": "unknown", "group_id": "speaker-01"}).encode(),
            headers={"Content-Type": "application/json"},
            method="PATCH",
        )
        with pytest.raises(HTTPError) as error:
            urlopen(request)
        assert error.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
