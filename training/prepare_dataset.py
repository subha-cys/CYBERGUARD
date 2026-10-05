"""Normalize an authorized source CSV into the strict training schema."""
import csv
import hashlib
import json
from pathlib import Path


def prepare_csv(source: str | Path, output: str | Path, text_column: str, label_column: str,
                phishing_label: str, benign_label: str) -> dict:
    seen = set()
    written = {"phishing": 0, "benign": 0, "duplicate_or_empty": 0}
    csv.field_size_limit(100_000_000)
    with Path(source).open("r", encoding="utf-8-sig", newline="") as src:
        reader = csv.DictReader(src)
        if not reader.fieldnames or text_column not in reader.fieldnames or label_column not in reader.fieldnames:
            raise ValueError(f"requested columns absent; available columns: {reader.fieldnames}")
        with Path(output).open("w", encoding="utf-8", newline="") as dst:
            writer = csv.DictWriter(dst, fieldnames=["text", "label"])
            writer.writeheader()
            for row in reader:
                text = (row.get(text_column) or "").strip()
                raw_label = (row.get(label_column) or "").strip().casefold()
                if raw_label == phishing_label.strip().casefold():
                    label = "phishing"
                elif raw_label == benign_label.strip().casefold():
                    label = "benign"
                else:
                    raise ValueError(f"unmapped label value {row.get(label_column)!r}; set explicit label mapping")
                key = (text, label)
                if not text or key in seen:
                    written["duplicate_or_empty"] += 1
                    continue
                seen.add(key)
                writer.writerow({"text": text, "label": label})
                written[label] += 1
    if min(written["phishing"], written["benign"]) < 10:
        raise ValueError(f"normalized data has too few rows per class: {written}")
    hasher = hashlib.sha256()
    with Path(output).open("rb") as normalized:
        for chunk in iter(lambda: normalized.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    written["normalized_sha256"] = digest
    manifest_path = Path(output).with_suffix(".manifest.json")
    source_manifest_path = Path(source).parent.parent / "manifest.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8")) if source_manifest_path.exists() else {}
    source_hash = hashlib.md5()
    with Path(source).open("rb") as source_bytes:
        for chunk in iter(lambda: source_bytes.read(1024 * 1024), b""):
            source_hash.update(chunk)
    published_md5 = source_manifest.get("source_md5")
    if published_md5 and source_hash.hexdigest().casefold() != published_md5.casefold():
        raise ValueError("source corpus MD5 does not match the dataset manifest")
    manifest_path.write_text(json.dumps({"source": Path(source).name, "source_text_column": text_column,
                                        "source_label_column": label_column, "phishing_label_value": phishing_label,
                                        "benign_label_value": benign_label, "source_md5": source_hash.hexdigest(),
                                        "source_dataset_manifest": source_manifest, "rows": written}, indent=2), encoding="utf-8")
    return written
