"""Stable, versioned login feature transformation shared by training and inference."""
from datetime import datetime

LOGIN_FEATURE_VERSION = "login-hour-failures-success-1.0.0"


def login_vector(event: dict) -> list[list[float]]:
    stamp = datetime.fromisoformat(str(event["timestamp"]).replace("Z", "+00:00"))
    return [[float(stamp.hour), float(event["failed_attempts"]), float(bool(event["successful_login"]))]]
