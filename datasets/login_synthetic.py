"""Seeded, explicitly synthetic login data generator for detector evaluation."""
import random
from datetime import datetime, timedelta, timezone


def generate_login_events(n: int = 1000, seed: int = 17) -> list[dict]:
    """Generate controlled normal/anomalous records; no real user history is implied."""
    if n < 20:
        raise ValueError("n must be at least 20")
    rng = random.Random(seed)
    start = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    events = []
    for i in range(n):
        anomaly = i % 5 == 0
        hour = rng.randrange(0, 5) if anomaly else rng.randrange(7, 21)
        failures = rng.randrange(5, 10) if anomaly else rng.randrange(0, 3)
        successful = bool(rng.randrange(2)) if anomaly else True
        stamp = (start + timedelta(days=i // 2)).replace(hour=hour)
        events.append({
            "user_id": f"synthetic-user-{i % 20:02d}", "timestamp": stamp.isoformat(),
            "ip": f"192.0.2.{(i % 200) + 1}", "country": "ZZ", "device_id": f"synthetic-device-{i % 30:02d}",
            "failed_attempts": failures, "successful_login": successful, "ground_truth_anomaly": anomaly,
        })
    return events

