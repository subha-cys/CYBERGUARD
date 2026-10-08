"""Local, feature-only memory for human-reviewed multimedia examples."""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from training.media import FEATURE_VERSION

LABELS = {"authentic", "synthetic"}
MODALITIES = {"audio", "image", "video"}
DERIVED_FEATURES = {
    "analysis_status",
    "authenticity_score",
    "byte_length",
    "confidence",
    "concern_level",
    "detected_indicators",
    "feature_extraction_error",
    "manipulation_indicator_score",
    "manipulation_probability",
    "sha256",
    "user_facing_limitation",
    "voice_origin",
}


def _connect(database_path: str | Path) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE IF NOT EXISTS learning_examples (
            sample_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            modality TEXT NOT NULL,
            feature_version TEXT NOT NULL,
            features_json TEXT NOT NULL,
            original_prediction TEXT NOT NULL,
            confirmed_label TEXT,
            group_id TEXT
        )"""
    )
    return connection


def numeric_feature_snapshot(features: dict[str, Any]) -> dict[str, float]:
    snapshot = {}
    for name, value in features.items():
        if name in DERIVED_FEATURES or isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        numeric = float(value)
        if math.isfinite(numeric):
            snapshot[name] = numeric
    return snapshot


def save_pending_example(
    database_path: str | Path,
    modality: str,
    features: dict[str, Any],
    prediction: str,
) -> str | None:
    if modality not in MODALITIES or prediction not in LABELS:
        return None
    snapshot = numeric_feature_snapshot(features)
    if not snapshot:
        return None
    sample_id = uuid4().hex
    with _connect(database_path) as db:
        db.execute(
            """INSERT INTO learning_examples
               (sample_id, created_at, modality, feature_version, features_json, original_prediction)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                sample_id,
                datetime.now(timezone.utc).isoformat(),
                modality,
                FEATURE_VERSION,
                json.dumps(snapshot, sort_keys=True, allow_nan=False),
                prediction,
            ),
        )
    return sample_id


def review_example(
    database_path: str | Path,
    sample_id: str,
    label: str,
    group_id: str,
) -> dict[str, Any]:
    if not isinstance(label, str) or label not in LABELS:
        raise ValueError("label must be authentic or synthetic")
    if not isinstance(group_id, str):
        raise ValueError("group_id must be a string")
    normalized_group = group_id.strip()
    if not 1 <= len(normalized_group) <= 200:
        raise ValueError("group_id must contain 1 to 200 characters")
    with _connect(database_path) as db:
        cursor = db.execute(
            """UPDATE learning_examples SET confirmed_label = ?, group_id = ?
               WHERE sample_id = ? AND confirmed_label IS NULL""",
            (label, normalized_group, sample_id),
        )
        if cursor.rowcount != 1:
            exists = db.execute(
                "SELECT confirmed_label FROM learning_examples WHERE sample_id = ?",
                (sample_id,),
            ).fetchone()
            if exists is None:
                raise ValueError("learning example was not found")
            raise ValueError("learning example was already reviewed and cannot be relabeled")
        row = db.execute(
            """SELECT sample_id, modality, confirmed_label, group_id
               FROM learning_examples WHERE sample_id = ?""",
            (sample_id,),
        ).fetchone()
    return dict(row)


def learning_summary(database_path: str | Path) -> dict[str, Any]:
    with _connect(database_path) as db:
        rows = db.execute(
            """SELECT modality,
                      COUNT(*) AS total,
                      SUM(CASE WHEN confirmed_label IS NULL THEN 1 ELSE 0 END) AS pending,
                      SUM(CASE WHEN confirmed_label = 'authentic' THEN 1 ELSE 0 END) AS authentic,
                      SUM(CASE WHEN confirmed_label = 'synthetic' THEN 1 ELSE 0 END) AS synthetic,
                      COUNT(DISTINCT CASE WHEN confirmed_label IS NOT NULL THEN group_id END) AS groups
               FROM learning_examples GROUP BY modality"""
        ).fetchall()
    counts = {
        modality: {"total": 0, "pending": 0, "authentic": 0, "synthetic": 0, "groups": 0}
        for modality in sorted(MODALITIES)
    }
    for row in rows:
        counts[row["modality"]] = {
            "total": int(row["total"]),
            "pending": int(row["pending"] or 0),
            "authentic": int(row["authentic"] or 0),
            "synthetic": int(row["synthetic"] or 0),
            "groups": int(row["groups"] or 0),
        }
    return {
        "examples": counts,
        "minimum_training_requirements": {
            "total_reviewed": 40,
            "per_label": 20,
            "distinct_source_groups": 8,
        },
        "raw_content_stored": False,
    }


def reviewed_examples(database_path: str | Path, modality: str) -> list[dict[str, Any]]:
    if modality not in MODALITIES:
        raise ValueError("modality must be audio, image, or video")
    with _connect(database_path) as db:
        rows = db.execute(
            """SELECT sample_id, feature_version, features_json, original_prediction,
                      confirmed_label, group_id
               FROM learning_examples
               WHERE modality = ? AND confirmed_label IS NOT NULL
               ORDER BY created_at, sample_id""",
            (modality,),
        ).fetchall()
    return [
        {
            "sample_id": row["sample_id"],
            "feature_version": row["feature_version"],
            "features": json.loads(row["features_json"]),
            "original_prediction": row["original_prediction"],
            "label": row["confirmed_label"],
            "group_id": row["group_id"],
        }
        for row in rows
    ]


def clear_learning_memory(database_path: str | Path) -> None:
    with _connect(database_path) as db:
        db.execute("DELETE FROM learning_examples")
