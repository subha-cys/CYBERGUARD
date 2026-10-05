import sqlite3

from backend import service


def test_prefilled_demo_analysis_is_not_persisted(tmp_path, monkeypatch):
    dashboard_db = tmp_path / "dashboard.sqlite3"
    incidents_db = tmp_path / "incidents.sqlite3"
    monkeypatch.setattr(service, "DASHBOARD_DB", dashboard_db)
    monkeypatch.setattr(service, "DEFAULT_DB", incidents_db)

    result = service.analyze_request({
        "type": "url",
        "url": "https://example.org/about",
        "synthetic_demo": True,
        "demo_id": "legitimate_url",
    }, persist_incident=False)

    assert result["input"]["synthetic_demo"] is True
    assert result["input"]["scenario"] == "legitimate_url"
    assert result.get("incident") is None
    assert not dashboard_db.exists()
    assert not incidents_db.exists()


def test_real_analysis_cannot_suppress_persistence_with_demo_payload(tmp_path, monkeypatch):
    dashboard_db = tmp_path / "dashboard.sqlite3"
    incidents_db = tmp_path / "incidents.sqlite3"
    monkeypatch.setattr(service, "DASHBOARD_DB", dashboard_db)
    monkeypatch.setattr(service, "DEFAULT_DB", incidents_db)

    result = service.analyze_request({
        "type": "url",
        "url": "http://192.0.2.14/login/update/account/verify?token=demo",
        "synthetic_demo": True,
        "demo_id": "arbitrary",
    })

    assert "synthetic_demo" not in result["input"]
    assert dashboard_db.exists()
    with sqlite3.connect(dashboard_db) as db:
        assert db.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 1


def test_real_analysis_keeps_existing_incident_persistence(tmp_path, monkeypatch):
    dashboard_db = tmp_path / "dashboard.sqlite3"
    incidents_db = tmp_path / "incidents.sqlite3"
    monkeypatch.setattr(service, "DASHBOARD_DB", dashboard_db)
    monkeypatch.setattr(service, "DEFAULT_DB", incidents_db)

    result = service.analyze_request({
        "type": "url",
        "url": "http://192.0.2.14/login/update/account/verify?token=demo",
    })

    assert "synthetic_demo" not in result["input"]
    assert dashboard_db.exists()
    with sqlite3.connect(dashboard_db) as db:
        assert db.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 1
