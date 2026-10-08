"""Video authenticity and temporal inconsistency feature extraction."""
from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from features.multimedia_image import extract_image_features

MAX_ANALYSIS_FRAME_DIMENSION = 1024


def _bound_frame(frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    scale = min(1.0, MAX_ANALYSIS_FRAME_DIMENSION / max(height, width))
    if scale < 1.0:
        return cv2.resize(
            frame,
            (max(1, round(width * scale)), max(1, round(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    return frame


def _compute_ssim(img1: np.ndarray, img2: np.ndarray) -> float:
    """Compute Structural Similarity Index (SSIM) between two grayscale frames."""
    # Ensure float32
    i1 = img1.astype(np.float32)
    i2 = img2.astype(np.float32)

    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2

    mu1 = cv2.GaussianBlur(i1, (11, 11), 1.5)
    mu2 = cv2.GaussianBlur(i2, (11, 11), 1.5)

    mu1_sq = mu1 * mu1
    mu2_sq = mu2 * mu2
    mu1_mu2 = mu1 * mu2

    sigma1_sq = cv2.GaussianBlur(i1 * i1, (11, 11), 1.5) - mu1_sq
    sigma2_sq = cv2.GaussianBlur(i2 * i2, (11, 11), 1.5) - mu2_sq
    sigma12 = cv2.GaussianBlur(i1 * i2, (11, 11), 1.5) - mu1_mu2

    ssim_map = ((2 * mu1_mu2 + c1) * (2 * sigma12 + c2)) / (
        (mu1_sq + mu2_sq + c1) * (sigma1_sq + sigma2_sq + c2)
    )
    return float(np.mean(ssim_map))


def _sample_video_frames(
    video_path: str | Path, max_frames: int = 24
) -> tuple[list[np.ndarray], dict[str, Any]]:
    """Sample video frames evenly using OpenCV VideoCapture."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(cap.get(cv2.CAP_PROP_FPS)) or 24.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = round(total_frames / max(1.0, fps), 2)

    if total_frames <= 0:
        # Fallback reading sequentially
        frames = []
        while len(frames) < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            frames.append(_bound_frame(frame))
        cap.release()
        return frames, {
            "total_frames": len(frames),
            "fps": fps,
            "width": width,
            "height": height,
            "duration_seconds": duration,
        }

    # Evenly spaced frame indices
    sample_count = min(max_frames, total_frames)
    indices = np.linspace(0, total_frames - 1, sample_count, dtype=int)

    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, frame = cap.read()
        if ret and frame is not None:
            frames.append(_bound_frame(frame))

    cap.release()
    return frames, {
        "total_frames": total_frames,
        "sampled_frames_count": len(frames),
        "fps": fps,
        "width": width,
        "height": height,
        "duration_seconds": duration,
    }


def extract_video_features(
    video_path: str | Path, max_frames: int = 24
) -> dict[str, Any]:
    """Extract temporal and visual authenticity features from video frames."""
    frames, meta = _sample_video_frames(video_path, max_frames=max_frames)
    if not frames:
        return {
            **meta,
            "temporal_continuity": "empty_or_unreadable",
            "mean_interframe_ssim": 1.0,
            "min_interframe_ssim": 1.0,
            "ssim_drop_count": 0,
            "optical_flow_jitter": 0.0,
            "luminance_flicker_ratio": 1.0,
        }

    # Grayscale frames downscaled for fast analysis
    grays = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
    # Standardize scale for consistent metric computation
    scaled_grays = [cv2.resize(g, (320, 240)) for g in grays]

    # 1. Temporal Continuity & Inter-Frame SSIM
    ssim_values = []
    diff_values = []
    luminance_means = []

    for i in range(len(scaled_grays) - 1):
        g1 = scaled_grays[i]
        g2 = scaled_grays[i + 1]

        ssim = _compute_ssim(g1, g2)
        ssim_values.append(ssim)

        diff = np.mean(np.abs(g1.astype(np.float32) - g2.astype(np.float32)))
        diff_values.append(float(diff))

        luminance_means.append(float(np.mean(g1)))

    if scaled_grays:
        luminance_means.append(float(np.mean(scaled_grays[-1])))

    mean_ssim = float(np.mean(ssim_values)) if ssim_values else 1.0
    min_ssim = float(np.min(ssim_values)) if ssim_values else 1.0
    # SSIM sudden drop threshold: drop > 0.15 from mean
    ssim_drops = sum(1 for s in ssim_values if (mean_ssim - s) > 0.15)

    # 2. Optical Flow Motion Smoothness & Boundary Jitter
    flow_magnitudes = []
    for i in range(len(scaled_grays) - 1):
        flow = cv2.calcOpticalFlowFarneback(
            scaled_grays[i],
            scaled_grays[i + 1],
            None,
            pyr_scale=0.5,
            levels=3,
            winsize=15,
            iterations=3,
            poly_n=5,
            poly_sigma=1.2,
            flags=0,
        )
        mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        flow_magnitudes.append(float(np.std(mag)))

    optical_flow_jitter = float(np.mean(flow_magnitudes)) if flow_magnitudes else 0.0

    # 3. Luminance / Color Temperature Flicker
    if luminance_means:
        lum_std = float(np.std(luminance_means))
        lum_mean = float(np.mean(luminance_means)) + 1e-5
        lum_flicker = round(lum_std / lum_mean, 4)
    else:
        lum_flicker = 0.0

    # 4. Keyframe Visual Artifacts (Sample middle keyframe)
    mid_idx = len(frames) // 2
    mid_rgb = cv2.cvtColor(frames[mid_idx], cv2.COLOR_BGR2RGB)
    keyframe_img = Image.fromarray(mid_rgb)
    keyframe_features = extract_image_features(keyframe_img)

    return {
        **meta,
        "mean_interframe_ssim": round(mean_ssim, 3),
        "min_interframe_ssim": round(min_ssim, 3),
        "ssim_drop_count": ssim_drops,
        "optical_flow_jitter": round(optical_flow_jitter, 3),
        "luminance_flicker_ratio": lum_flicker,
        "keyframe_fft_spike": keyframe_features.get("fft_high_freq_spike", 0.0),
        "keyframe_ela_discrepancy": keyframe_features.get("ela_patch_discrepancy_ratio", 1.0),
        "keyframe_noise_ratio": keyframe_features.get("noise_variance_quadrant_ratio", 1.0),
    }
