"""Image authenticity and manipulation feature extraction."""
from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def _compute_ela(img: Image.Image, quality: int = 90) -> dict[str, float]:
    """Perform Error Level Analysis (ELA) by measuring recompression error."""
    # Ensure RGB
    rgb = img.convert("RGB")
    buf = io.BytesIO()
    rgb.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    recompressed = Image.open(buf).convert("RGB")

    orig_arr = np.asarray(rgb, dtype=np.float32)
    recomp_arr = np.asarray(recompressed, dtype=np.float32)

    diff = np.abs(orig_arr - recomp_arr)
    # Scaled difference
    mean_err = float(np.mean(diff))
    max_err = float(np.max(diff))
    std_err = float(np.std(diff))

    # Spatial patch discrepancy (16x16 grid)
    h, w, _ = diff.shape
    patch_h = max(8, h // 8)
    patch_w = max(8, w // 8)
    patch_means = []
    for y in range(0, h - patch_h + 1, patch_h):
        for x in range(0, w - patch_w + 1, patch_w):
            patch = diff[y:y + patch_h, x:x + patch_w]
            patch_means.append(float(np.mean(patch)))

    discrepancy_ratio = 1.0
    if patch_means:
        p_min = min(patch_means)
        p_max = max(patch_means)
        discrepancy_ratio = round((p_max + 1e-5) / (p_min + 1e-5), 3)

    return {
        "ela_mean_error": round(mean_err, 3),
        "ela_max_error": round(max_err, 3),
        "ela_std_error": round(std_err, 3),
        "ela_patch_discrepancy_ratio": discrepancy_ratio,
    }


def _compute_fft_spectral_artifacts(gray: np.ndarray, num_bins: int = 32) -> dict[str, float]:
    """Compute 2D FFT azimuthal radial power spectrum and detect generative grid spikes."""
    h, w = gray.shape
    # Center crop to square if needed for cleaner radial bins
    min_dim = min(h, w)
    cy, cx = h // 2, w // 2
    cropped = gray[cy - min_dim // 2: cy + min_dim // 2, cx - min_dim // 2: cx + min_dim // 2]
    ch, cw = cropped.shape

    # Apply Hann window to reduce boundary leak
    window_y = np.hanning(ch)
    window_x = np.hanning(cw)
    window_2d = np.outer(window_y, window_x)
    windowed = (cropped - np.mean(cropped)) * window_2d

    # 2D FFT
    fft = np.fft.fftshift(np.fft.fft2(windowed))
    power = np.log1p(np.abs(fft) ** 2)

    # Radial distance matrix from center
    y, x = np.ogrid[:ch, :cw]
    center = (ch // 2, cw // 2)
    radius = np.hypot(x - center[1], y - center[0])
    max_radius = ch / 2.0

    # Azimuthal average across radial rings
    bin_edges = np.linspace(0, max_radius, num_bins + 1)
    radial_profile = []
    for i in range(num_bins):
        mask = (radius >= bin_edges[i]) & (radius < bin_edges[i + 1])
        if np.any(mask):
            radial_profile.append(float(np.mean(power[mask])))
        else:
            radial_profile.append(0.0)

    # Detect high-frequency spikes above local polynomial baseline
    profile_arr = np.array(radial_profile, dtype=np.float32)
    # Check upper half (high frequencies)
    high_freq = profile_arr[num_bins // 2:]
    if len(high_freq) > 3:
        # Fit linear baseline
        x_idx = np.arange(len(high_freq))
        poly = np.polyfit(x_idx, high_freq, 1)
        baseline = np.polyval(poly, x_idx)
        residuals = high_freq - baseline
        max_spike = float(np.max(residuals))
        std_residuals = float(np.std(residuals))
    else:
        max_spike = 0.0
        std_residuals = 0.0

    # 2D spectral peak prominence outside DC center
    hf_mask = (radius > 25) & (radius < max_radius)
    if np.any(hf_mask):
        hf_power = np.abs(fft)[hf_mask] ** 2
        med = float(np.median(hf_power)) + 1e-5
        p99 = float(np.percentile(hf_power, 99.5))
        peak_prominence = round(p99 / med, 2)
    else:
        peak_prominence = 1.0

    return {
        "fft_high_freq_spike": round(max_spike, 3),
        "fft_residual_std": round(std_residuals, 3),
        "fft_hf_energy_ratio": round(float(np.mean(high_freq)) / (float(np.mean(profile_arr)) + 1e-6), 3),
        "fft_peak_prominence": peak_prominence,
    }


def _compute_noise_residuals(gray: np.ndarray) -> dict[str, float]:
    """Estimate camera PRNU/noise residuals and measure patch-wise variance inconsistency."""
    # Approximate noise residual via simple 3x3 median filter subtraction
    try:
        from scipy.ndimage import median_filter
        filtered = median_filter(gray, size=3)
    except Exception:
        # Fallback simple 3x3 box blur
        padded = np.pad(gray, 1, mode="edge")
        filtered = (padded[:-2, :-2] + padded[:-2, 1:-1] + padded[:-2, 2:] +
                    padded[1:-1, :-2] + padded[1:-1, 1:-1] + padded[1:-1, 2:] +
                    padded[2:, :-2] + padded[2:, 1:-1] + padded[2:, 2:]) / 9.0

    noise_residual = gray.astype(np.float32) - filtered.astype(np.float32)

    # Divide into 4 quadrants to detect uneven sensor noise distribution
    h, w = gray.shape
    mid_y, mid_x = h // 2, w // 2
    q1 = noise_residual[:mid_y, :mid_x]
    q2 = noise_residual[:mid_y, mid_x:]
    q3 = noise_residual[mid_y:, :mid_x]
    q4 = noise_residual[mid_y:, mid_x:]

    vars_ = [float(np.var(q)) for q in (q1, q2, q3, q4) if q.size > 0]
    if vars_ and min(vars_) > 1e-6:
        noise_var_ratio = round(max(vars_) / min(vars_), 3)
    else:
        noise_var_ratio = 1.0

    total_noise_std = round(float(np.std(noise_residual)), 3)
    return {
        "noise_residual_std": total_noise_std,
        "noise_variance_quadrant_ratio": noise_var_ratio,
    }


def _compute_lighting_and_edges(gray: np.ndarray) -> dict[str, float]:
    """Compute illumination gradients and boundary sharpness for seam detection."""
    # Sobel gradients
    try:
        from scipy.ndimage import sobel
        gx = sobel(gray, axis=1)
        gy = sobel(gray, axis=0)
    except Exception:
        gx = np.gradient(gray.astype(np.float32), axis=1)
        gy = np.gradient(gray.astype(np.float32), axis=0)

    magnitude = np.hypot(gx, gy)
    angles = np.arctan2(gy, gx)

    # Edge sharpness / seam metric (ratio of 99th percentile gradient to median gradient)
    p99 = float(np.percentile(magnitude, 99))
    p50 = float(np.median(magnitude)) + 1e-5
    edge_contrast_ratio = round(p99 / p50, 3)

    # Lighting direction uniformity: circular variance of gradient angles
    sin_sum = float(np.mean(np.sin(angles)))
    cos_sum = float(np.mean(np.cos(angles)))
    resultant = math.sqrt(sin_sum ** 2 + cos_sum ** 2)
    directional_coherence = round(resultant, 3)

    return {
        "edge_contrast_ratio": edge_contrast_ratio,
        "lighting_directional_coherence": directional_coherence,
    }


def extract_image_features(image_input: str | Path | bytes | Image.Image) -> dict[str, Any]:
    """Extract comprehensive authenticity indicators from an image."""
    if isinstance(image_input, Image.Image):
        img = image_input
    elif isinstance(image_input, (str, Path)):
        img = Image.open(str(image_input))
    elif isinstance(image_input, bytes):
        img = Image.open(io.BytesIO(image_input))
    else:
        raise TypeError(f"Unsupported image input type: {type(image_input)}")

    rgb = img.convert("RGB")
    width, height = rgb.size
    gray = np.asarray(rgb.convert("L"), dtype=np.float32)

    # 1. Error Level Analysis
    ela_res = _compute_ela(rgb, quality=90)

    # 2. 2D-FFT Spectral Analysis
    fft_res = _compute_fft_spectral_artifacts(gray, num_bins=32)

    # 3. Noise Residual Consistency
    noise_res = _compute_noise_residuals(gray)

    # 4. Lighting & Edge Seam Consistency
    lighting_res = _compute_lighting_and_edges(gray)

    return {
        "width": width,
        "height": height,
        "aspect_ratio": round(width / max(1, height), 3),
        **ela_res,
        **fft_res,
        **noise_res,
        **lighting_res,
    }
