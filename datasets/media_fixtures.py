"""Safe, authorized synthetic multimedia fixtures for deepfake and authenticity testing."""
from __future__ import annotations

import io
import math
import struct
import wave
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

FIXTURES_DIR = Path(__file__).resolve().parent / "media_fixtures"


def get_fixtures_dir() -> Path:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    return FIXTURES_DIR


def create_normal_image_fixture() -> Path:
    """Generate a clean, photographic-like synthetic image fixture."""
    out_path = get_fixtures_dir() / "normal_image.jpg"
    w, h = 320, 240
    # Natural gradient background
    y, x = np.mgrid[:h, :w]
    bg = 120 + 40 * np.sin(x / 50.0) + 30 * np.cos(y / 40.0)
    # Add circular foreground object with smooth edges
    dist = np.hypot(x - w // 2, y - h // 2)
    fg_mask = np.clip((70 - dist) / 5.0, 0, 1)
    img_data = (1.0 - fg_mask) * bg + fg_mask * (180 + 20 * np.sin(dist / 10.0))
    # Add natural camera sensor Gaussian noise
    np.random.seed(42)
    noise = np.random.normal(0, 3.0, (h, w))
    final = np.clip(img_data + noise, 0, 255).astype(np.uint8)

    # 3-channel RGB
    rgb = np.stack([final, np.clip(final * 0.95, 0, 255).astype(np.uint8), np.clip(final * 0.9, 0, 255).astype(np.uint8)], axis=-1)
    pil_img = Image.fromarray(rgb)
    pil_img.save(str(out_path), "JPEG", quality=92)
    return out_path


def create_manipulated_image_fixture() -> Path:
    """Generate a synthetic manipulated image fixture with splicing, ELA discrepancy, and FFT grid spikes."""
    out_path = get_fixtures_dir() / "manipulated_image.jpg"
    w, h = 320, 240
    y, x = np.mgrid[:h, :w]

    # Background texture
    bg = 110 + 35 * np.sin(x / 40.0)
    rgb = np.stack([bg, bg, bg], axis=-1).astype(np.uint8)
    base_img = Image.fromarray(rgb)

    # Pre-compress background at low quality 50
    buf = io.BytesIO()
    base_img.save(buf, format="JPEG", quality=50)
    buf.seek(0)
    compressed_bg = np.asarray(Image.open(buf).convert("RGB"), dtype=np.float32)

    # High-quality spliced patch in center (simulating face swap)
    patch_size = 90
    cy, cx = h // 2, w // 2
    py, px = np.mgrid[:patch_size, :patch_size]
    # Spliced face with AI generative checkerboard frequency pattern
    grid_artifact = 18.0 * np.sin(2.0 * math.pi * px / 4.0) * np.sin(2.0 * math.pi * py / 4.0)
    spliced_patch = 200 + 30 * np.cos(px / 12.0) + grid_artifact

    # Insert patch into center with sharp boundary seam
    y1, y2 = cy - patch_size // 2, cy + patch_size // 2
    x1, x2 = cx - patch_size // 2, cx + patch_size // 2
    for c in range(3):
        compressed_bg[y1:y2, x1:x2, c] = spliced_patch

    final = np.clip(compressed_bg, 0, 255).astype(np.uint8)
    pil_img = Image.fromarray(final)
    # Save at high quality to preserve splicing discrepancy
    pil_img.save(str(out_path), "JPEG", quality=95)
    return out_path


def create_normal_audio_fixture() -> Path:
    """Generate a natural synthetic speech audio fixture with organic jitter, harmonics, and room tone."""
    out_path = get_fixtures_dir() / "normal_audio.wav"
    sr = 16000
    duration = 2.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)

    # Fundamental frequency ~180 Hz with natural organic pitch jitter (0.6%)
    np.random.seed(42)
    jitter_drift = np.cumsum(np.random.normal(0, 0.003, len(t)))
    jitter_drift = jitter_drift - np.mean(jitter_drift)
    f0 = 180.0 * (1.0 + jitter_drift)
    phase = 2.0 * math.pi * np.cumsum(f0) / sr

    # Harmonics: H1, H2, H3, H4, H5 with natural vocal rolloff
    signal = (
        0.55 * np.sin(phase) +
        0.30 * np.sin(2.0 * phase) +
        0.18 * np.sin(3.0 * phase) +
        0.10 * np.sin(4.0 * phase) +
        0.05 * np.sin(5.0 * phase)
    )

    # Natural amplitude shimmer (modest amplitude variation)
    shimmer = 1.0 + 0.03 * np.sin(2.0 * math.pi * 5.0 * t)
    signal = signal * shimmer

    # Natural room acoustic noise floor (-42 dB)
    room_noise = np.random.normal(0, 0.015, len(t))
    full_audio = np.clip(signal * 0.7 + room_noise, -1.0, 1.0)

    # Write 16-bit PCM WAV
    int16_audio = (full_audio * 32767.0).astype(np.int16)
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(int16_audio.tobytes())

    return out_path


def create_synthetic_audio_fixture() -> Path:
    """Generate a synthetic vocoder-style audio fixture with brick-wall cutoff and rigid pitch."""
    out_path = get_fixtures_dir() / "synthetic_audio.wav"
    sr = 16000
    duration = 2.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)

    # Perfectly rigid F0 without human micro-jitter (robotic periodicity)
    f0 = 190.0
    phase = 2.0 * math.pi * f0 * t

    # Square / pulse wave harmonics typical of synthetic buzz
    raw_signal = (
        0.60 * np.sin(phase) +
        0.40 * np.sin(2.0 * phase) +
        0.25 * np.sin(3.0 * phase) +
        0.15 * np.sin(4.0 * phase)
    )

    # Strict brick-wall lowpass cutoff at 4.2 kHz (no acoustic energy above cutoff)
    # Filter in frequency domain
    fft_spec = np.fft.rfft(raw_signal)
    freqs = np.fft.rfftfreq(len(t), 1.0 / sr)
    fft_spec[freqs > 4200] = 0.0  # Zero out upper spectrum
    filtered_signal = np.fft.irfft(fft_spec, n=len(t))

    # Add digital silence dropouts in between phrases
    silence_start = int(sr * 0.8)
    silence_end = int(sr * 1.1)
    filtered_signal[silence_start:silence_end] = 0.0  # Exact digital zero

    full_audio = np.clip(filtered_signal * 0.8, -1.0, 1.0)
    int16_audio = (full_audio * 32767.0).astype(np.int16)

    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(int16_audio.tobytes())

    return out_path


def create_normal_video_fixture() -> Path:
    """Generate a normal synthetic video fixture with continuous motion and high SSIM."""
    out_path = get_fixtures_dir() / "normal_video.avi"
    w, h = 320, 240
    fps = 15.0
    n_frames = 20

    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (w, h))

    np.random.seed(42)
    # Smooth moving circle across frames
    for i in range(n_frames):
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        # Consistent textured background
        frame[:] = (70, 75, 80)
        # Object moves linearly by 3 pixels per frame
        cx = int(80 + i * 5)
        cy = 120
        cv2.circle(frame, (cx, cy), 35, (160, 210, 180), -1)
        # Natural slight camera noise
        noise = np.random.normal(0, 2.0, (h, w, 3)).astype(np.int16)
        frame_noisy = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        writer.write(frame_noisy)

    writer.release()
    return out_path


def create_manipulated_video_fixture() -> Path:
    """Generate a manipulated video fixture with spliced frames, sudden SSIM drops, and temporal flicker."""
    out_path = get_fixtures_dir() / "manipulated_video.avi"
    w, h = 320, 240
    fps = 15.0
    n_frames = 20

    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (w, h))

    for i in range(n_frames):
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:] = (70, 75, 80)

        if 8 <= i <= 11:
            # Spliced deepfake segment: sudden position teleport, exposure flash, and warped boundary
            cx = int(200 + ((i - 8) % 2) * 50)  # Teleport motion jitter
            cy = int(80 + ((i - 8) % 3) * 35)
            frame[:] = (130, 140, 160)  # Sudden lighting jump
            cv2.ellipse(frame, (cx, cy), (55, 30), 45, 0, 360, (230, 140, 120), -1)
        else:
            cx = int(80 + i * 5)
            cy = 120
            cv2.circle(frame, (cx, cy), 35, (160, 210, 180), -1)

        writer.write(frame)

    writer.release()
    return out_path


def ensure_all_fixtures() -> dict[str, Path]:
    """Ensure all 6 safe synthetic fixtures are generated and return their paths."""
    return {
        "normal_image": create_normal_image_fixture(),
        "synthetic_manipulated_image": create_manipulated_image_fixture(),
        "normal_audio": create_normal_audio_fixture(),
        "synthetic_audio": create_synthetic_audio_fixture(),
        "normal_video": create_normal_video_fixture(),
        "manipulated_video": create_manipulated_video_fixture(),
    }
