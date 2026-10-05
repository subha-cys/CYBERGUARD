"""Multimedia detection configuration and system capability inspection."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

CONFIG_FILE = Path(__file__).resolve().parent / "multimedia_settings.json"


def check_system_capabilities() -> dict[str, Any]:
    """Inspect environment for media processing capabilities."""
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")

    has_cv2 = False
    cv2_version = None
    try:
        import cv2  # noqa: F401
        has_cv2 = True
        cv2_version = getattr(cv2, "__version__", "unknown")
    except ImportError:
        pass

    has_scipy = False
    scipy_version = None
    try:
        import scipy  # noqa: F401
        has_scipy = True
        scipy_version = getattr(scipy, "__version__", "unknown")
    except ImportError:
        pass

    has_pil = False
    pil_version = None
    try:
        import PIL  # noqa: F401
        has_pil = True
        pil_version = getattr(PIL, "__version__", "unknown")
    except ImportError:
        pass

    ffmpeg_install_guide = None
    if not ffmpeg_path:
        if sys.platform == "win32":
            ffmpeg_install_guide = (
                "FFmpeg is not installed on system PATH. To install on Windows:\n"
                "  winget install Gyan.FFmpeg\n"
                "or with Chocolatey:\n"
                "  choco install ffmpeg\n"
                "OpenCV and PIL provide native video and image processing without requiring FFmpeg."
            )
        elif sys.platform == "darwin":
            ffmpeg_install_guide = "Install via Homebrew: brew install ffmpeg"
        else:
            ffmpeg_install_guide = "Install via apt: sudo apt install ffmpeg"

    return {
        "ffmpeg_available": bool(ffmpeg_path),
        "ffmpeg_path": ffmpeg_path,
        "ffprobe_available": bool(ffprobe_path),
        "ffmpeg_install_guide": ffmpeg_install_guide,
        "opencv_available": has_cv2,
        "opencv_version": cv2_version,
        "scipy_available": has_scipy,
        "scipy_version": scipy_version,
        "pillow_available": has_pil,
        "pillow_version": pil_version,
        "execution_device": "cpu",
        "cpu_threads": os.cpu_count() or 4,
    }


def get_multimedia_config() -> dict[str, Any]:
    """Retrieve current multimedia configuration with lightweight/advanced options."""
    defaults = {
        "model_mode": "lightweight",  # "lightweight" or "advanced"
        "image_analysis": {
            "ela_quality": 90,
            "fft_radial_bins": 32,
            "noise_patch_size": 32,
            "ela_threshold": 12.0,
            "fft_spike_threshold": 2.2,
        },
        "video_analysis": {
            "max_sampled_frames": 24,
            "frame_sample_rate_fps": 1.0,
            "ssim_drop_threshold": 0.15,
            "optical_flow_jitter_threshold": 3.5,
        },
        "audio_analysis": {
            "sample_rate_target": 16000,
            "vocoder_cutoff_threshold_hz": 8000,
            "natural_jitter_min": 0.002,
            "natural_shimmer_min": 0.015,
            "silence_threshold_db": -50.0,
        },
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                defaults.update(saved)
        except Exception:
            pass
    return defaults


def update_multimedia_config(updates: dict[str, Any]) -> dict[str, Any]:
    """Persist updated configuration settings."""
    cfg = get_multimedia_config()
    cfg.update(updates)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass
    return cfg
