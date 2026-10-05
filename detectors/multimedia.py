"""Multimedia authenticity and deepfake detection engine."""
from __future__ import annotations

import abc
import hashlib
import json
import math
import shutil
import struct
import subprocess
import tempfile
import time
import wave
from pathlib import Path
from typing import Any

from config.multimedia_config import get_multimedia_config
from detectors.contract import DetectorResult
from features.multimedia_audio import extract_audio_features
from features.multimedia_image import extract_image_features
from features.multimedia_video import extract_video_features

DETECTOR_VERSION = "multimedia-authenticity-2.0.0"
MAX_FILE_BYTES = 100 * 1024 * 1024
EPISTEMIC_LIMITATION = (
    "Classification is a statistical model prediction and does not represent definitive proof of manipulation. "
    "Forensic verification requires source provenance and manual cryptographic inspection."
)


class ImageManipulationModel(abc.ABC):
    """Adapter contract. Implementations must document evaluation and return a result dict."""
    model_version: str
    evaluation_reference: str

    @abc.abstractmethod
    def analyze(self, path: Path, features: dict[str, Any]) -> dict[str, Any]:
        """Return classification/evidence and optional calibrated confidence, never a fabricated score."""


class AudioDeepfakeModel(abc.ABC):
    """Adapter contract for evaluated synthetic-speech models."""
    model_version: str
    evaluation_reference: str

    @abc.abstractmethod
    def analyze(self, path: Path, features: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class VideoDeepfakeModel(abc.ABC):
    """Adapter contract for evaluated video models, optionally consuming sampled frames/audio."""
    model_version: str
    evaluation_reference: str

    @abc.abstractmethod
    def analyze(self, path: Path, features: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


def _result(
    classification: str,
    *,
    method: str = "multimodal_heuristic",
    evidence=None,
    features=None,
    limitations=None,
    confidence=None,
    model_version=None,
    elapsed=0.0,
) -> DetectorResult:
    output_features = dict(features or {})
    output_features.setdefault("user_facing_limitation", EPISTEMIC_LIMITATION)
    return DetectorResult(
        "multimedia_assessment",
        DETECTOR_VERSION,
        method,
        classification,
        confidence,
        evidence or [],
        output_features,
        limitations or [EPISTEMIC_LIMITATION],
        elapsed,
        model_version=model_version or DETECTOR_VERSION,
        confidence_status="unavailable" if confidence is None else "model_reported",
    )


def _validate_file(path: str | Path) -> tuple[Path, bytes]:
    p = Path(path)
    if not p.is_file():
        raise ValueError("media path must identify an existing regular file")
    size = p.stat().st_size
    if size <= 0 or size > MAX_FILE_BYTES:
        raise ValueError(f"media file must be between 1 byte and {MAX_FILE_BYTES} bytes")
    with p.open("rb") as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) != size:
        raise ValueError("file changed or exceeded size limit during read")
    return p, data


def _image_header(data: bytes) -> dict[str, Any] | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 33 and data[12:16] == b"IHDR":
        width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", data[16:29])
        return {"format": "PNG", "width": width, "height": height, "bit_depth": depth,
                "color_type": color, "compression_method": compression, "interlace_method": interlace,
                "metadata_chunks_present": any(k in data for k in (b"eXIf", b"tEXt", b"iTXt", b"zTXt"))}
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        return {"format": "GIF", "width": int.from_bytes(data[6:8], "little"), "height": int.from_bytes(data[8:10], "little"),
                "color_table_present": bool(data[10] & 0x80) if len(data) > 10 else None}
    if data.startswith(b"BM") and len(data) >= 26:
        return {"format": "BMP", "width": abs(int.from_bytes(data[18:22], "little", signed=True)),
                "height": abs(int.from_bytes(data[22:26], "little", signed=True)),
                "bits_per_pixel": int.from_bytes(data[28:30], "little") if len(data) >= 30 else None}
    if data.startswith(b"\xff\xd8"):
        pos = 2
        while pos + 4 <= len(data):
            if data[pos] != 0xFF:
                pos += 1
                continue
            marker = data[pos + 1]
            pos += 2
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                continue
            if pos + 2 > len(data):
                break
            size = int.from_bytes(data[pos:pos + 2], "big")
            if size < 2 or pos + size > len(data):
                break
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                if size >= 7:
                    height, width = struct.unpack(">HH", data[pos + 3:pos + 7])
                    return {"format": "JPEG", "width": width, "height": height,
                            "metadata_segments_present": any(x in data for x in (b"Exif\x00\x00", b"http://ns.adobe.com/xap/1.0")),
                            "jpeg_quantization_tables_present": b"\xff\xdb" in data}
            pos += size
    if data.startswith(b"RIFF") and len(data) >= 16 and data[8:12] == b"WEBP":
        kind = data[12:16].decode("ascii", "replace")
        return {"format": "WEBP", "container_chunk": kind, "metadata_chunks_present": any(x in data for x in (b"EXIF", b"XMP "))}
    return None


def _optional_model(model, path: Path, features: dict, modality: str):
    if model is None:
        return None
    if not getattr(model, "evaluation_reference", None) or not getattr(model, "model_version", None):
        raise ValueError(f"{modality} model adapter must identify its model version and evaluation reference")
    result = model.analyze(path, features)
    if not isinstance(result, dict) or result.get("classification") not in {
        "manipulation_indicators_detected",
        "suspicious",
        "no_significant_indicators",
        "inconclusive",
        "unsupported",
    }:
        raise ValueError("model adapter returned an unsupported classification")
    confidence = result.get("confidence")
    if confidence is not None and (not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1):
        raise ValueError("model adapter confidence must be null or in [0, 1]")
    evidence = list(result.get("evidence", []))
    evidence.append({"indicator": "model_evaluation_reference", "value": model.evaluation_reference})
    return result, evidence


def _determine_concern(probability: float) -> tuple[str, str]:
    """Map calibrated probability to concern level and classifier label."""
    if probability >= 0.70:
        return "HIGH CONCERN", "manipulation_indicators_detected"
    if probability >= 0.35:
        return "MODERATE CONCERN", "suspicious"
    return "LOW CONCERN", "no_significant_indicators"


def analyze_image(path: str | Path, model: ImageManipulationModel | None = None) -> DetectorResult:
    """Analyze image for manipulation, synthetic generation artifacts, and authenticity."""
    start = time.perf_counter()
    p, data = _validate_file(path)
    header = _image_header(data)
    if not header:
        return _result(
            "unsupported",
            features={"byte_length": len(data), "sha256": hashlib.sha256(data).hexdigest()},
            limitations=["Unsupported or unrecognized image format.", EPISTEMIC_LIMITATION],
            elapsed=(time.perf_counter() - start) * 1000,
        )

    # Extract deep authentic indicators
    try:
        features = extract_image_features(p)
    except Exception as exc:
        features = {"extraction_error": str(exc)}

    evidence = [{"indicator": "image_format_metadata", "type": "observed_file_property", "value": header}]
    detected_indicators = []
    prob_score = 0.04  # baseline benign

    ela_ratio = features.get("ela_patch_discrepancy_ratio", 1.0)
    fft_prominence = features.get("fft_peak_prominence", 1.0)
    fft_spike = features.get("fft_high_freq_spike", 0.0)
    noise_ratio = features.get("noise_variance_quadrant_ratio", 1.0)
    edge_contrast = features.get("edge_contrast_ratio", 1.0)

    # 1. Error Level Analysis (Compression Inconsistency)
    if ela_ratio >= 15.0:
        prob_score += 0.45
        ind = "compression_inconsistency_ela"
        evidence.append({"indicator": ind, "type": "compression_analysis", "value": f"discrepancy ratio {ela_ratio:.1f}"})
        detected_indicators.append("Significant local recompression error variance (ELA) indicating splicing or composite layers.")
    elif ela_ratio >= 3.0:
        prob_score += 0.25
        ind = "compression_inconsistency_ela"
        evidence.append({"indicator": ind, "type": "compression_analysis", "value": f"discrepancy ratio {ela_ratio:.1f}"})
        detected_indicators.append("Moderate compression inconsistency across image segments.")

    # 2. 2D FFT Spectral Generative Grid Spikes
    if fft_prominence >= 120.0 or fft_spike >= 2.0:
        prob_score += 0.45
        ind = "spectral_grid_artifacts"
        evidence.append({"indicator": ind, "type": "frequency_analysis", "value": f"peak prominence {fft_prominence:.1f}"})
        detected_indicators.append("Periodic high-frequency spectral peaks characteristic of generative model deconvolution kernels.")
    elif fft_prominence >= 50.0 or fft_spike >= 1.2:
        prob_score += 0.20
        ind = "spectral_grid_artifacts"
        evidence.append({"indicator": ind, "type": "frequency_analysis", "value": f"peak prominence {fft_prominence:.1f}"})
        detected_indicators.append("Subtle high-frequency spectral grid irregularities.")

    # 3. Noise Residual Inconsistency
    if noise_ratio >= 2.8:
        prob_score += 0.25
        ind = "noise_residual_inconsistency"
        evidence.append({"indicator": ind, "type": "sensor_noise", "value": f"variance ratio {noise_ratio:.2f}"})
        detected_indicators.append("Discontinuous PRNU sensor noise floor across spatial quadrants.")

    # 4. Sharp Boundary Seams
    if edge_contrast >= 18.0 and ela_ratio >= 2.5:
        prob_score += 0.15
        ind = "blending_seam_detected"
        evidence.append({"indicator": ind, "type": "edge_analysis", "value": f"edge contrast {edge_contrast:.1f}"})
        detected_indicators.append("Sharp transition boundaries around foreground regions.")

    manip_prob = round(min(0.96, max(0.03, prob_score)), 4)
    auth_score = round(1.0 - manip_prob, 4)
    concern_level, classification = _determine_concern(manip_prob)
    confidence = round(min(0.95, 0.70 + 0.05 * len(detected_indicators)), 2)

    features.update({
        "authenticity_score": auth_score,
        "manipulation_probability": manip_prob,
        "confidence": confidence,
        "concern_level": concern_level,
        "detected_indicators": detected_indicators,
    })

    limitations = [
        EPISTEMIC_LIMITATION,
        "Image compression history and social-media re-encoding can influence high-frequency metrics.",
    ]

    model_output = _optional_model(model, p, features, "image")
    method, model_version = "signal_and_compression_heuristics", None
    if model_output:
        output, model_evidence = model_output
        classification = output["classification"]
        evidence.extend(model_evidence)
        limitations.extend(output.get("limitations", []))
        method, model_version, confidence = "ml", model.model_version, output.get("confidence")

    elapsed = (time.perf_counter() - start) * 1000
    return _result(
        classification,
        method=method,
        evidence=evidence,
        features=features,
        limitations=limitations,
        confidence=confidence,
        model_version=model_version,
        elapsed=elapsed,
    )


def analyze_audio(path: str | Path, model: AudioDeepfakeModel | None = None) -> DetectorResult:
    """Analyze audio/voice recording for synthetic speech, vocoder cutoffs, and acoustic anomalies."""
    start = time.perf_counter()
    p, data = _validate_file(path)
    evidence = []
    detected_indicators = []

    try:
        features = extract_audio_features(p)
    except Exception as exc:
        features = {"byte_length": len(data), "sha256": hashlib.sha256(data).hexdigest(), "extraction_error": str(exc)}

    evidence.append({
        "indicator": "audio_stream_properties",
        "type": "observed_file_property",
        "value": {
            "sample_rate_hz": features.get("sample_rate_hz"),
            "duration_seconds": features.get("duration_seconds"),
        },
    })

    prob_score = 0.04  # baseline benign

    hf_ratio = features.get("high_frequency_energy_ratio", 0.01)
    rolloff = features.get("spectral_rolloff_hz", 7000.0)
    jitter = features.get("vocal_jitter", 0.01)
    f0_std = features.get("f0_std_hz", 20.0)
    silence_frac = features.get("digital_silence_fraction", 0.0)

    # 1. Neural Vocoder Brick-Wall Cutoff
    if hf_ratio < 0.00005 and rolloff <= 5500:
        prob_score += 0.45
        ind = "synthetic_vocoder_cutoff"
        evidence.append({"indicator": ind, "type": "spectral_analysis", "value": f"cutoff rolloff {rolloff}Hz, HF ratio {hf_ratio}"})
        detected_indicators.append("Sharp brick-wall frequency cutoff characteristic of neural vocoder synthesis (e.g. HiFi-GAN/MelGAN).")
    elif hf_ratio < 0.0005:
        prob_score += 0.20
        ind = "synthetic_vocoder_cutoff"
        evidence.append({"indicator": ind, "type": "spectral_analysis", "value": f"HF ratio {hf_ratio}"})
        detected_indicators.append("Unusually low high-frequency acoustic presence.")

    # 2. Vocal Micro-Variation (Jitter Perturbation)
    if jitter < 0.001 and features.get("mean_f0_hz", 0) > 60:
        prob_score += 0.40
        ind = "low_vocal_microvariation"
        evidence.append({"indicator": ind, "type": "voice_mechanics", "value": f"vocal jitter {jitter:.5f}"})
        detected_indicators.append("Abnormally low vocal micro-jitter; speech exhibits mechanical, non-biological periodicity.")

    # 3. Monotone Robotic Pitch
    if f0_std < 5.0 and features.get("mean_f0_hz", 0) > 60:
        prob_score += 0.25
        ind = "robotic_pitch_stability"
        evidence.append({"indicator": ind, "type": "pitch_tracking", "value": f"F0 std {f0_std:.1f}Hz"})
        detected_indicators.append("Unnaturally flat pitch contour lacking human prosodic variation.")

    # 4. Digital Silence Dropouts
    if silence_frac >= 0.08:
        prob_score += 0.20
        ind = "unnatural_silence_dropout"
        evidence.append({"indicator": ind, "type": "temporal_silence", "value": f"silence fraction {silence_frac:.2f}"})
        detected_indicators.append("Artificial digital zero-energy dropouts rather than natural room acoustic ambiance.")

    manip_prob = round(min(0.96, max(0.03, prob_score)), 4)
    auth_score = round(1.0 - manip_prob, 4)
    concern_level, classification = _determine_concern(manip_prob)
    confidence = round(min(0.95, 0.70 + 0.05 * len(detected_indicators)), 2)

    features.update({
        "authenticity_score": auth_score,
        "manipulation_probability": manip_prob,
        "confidence": confidence,
        "concern_level": concern_level,
        "detected_indicators": detected_indicators,
    })

    limitations = [
        EPISTEMIC_LIMITATION,
        "Acoustic spectral cutoffs can also occur in bandlimited telephone or low-bitrate compression channels.",
    ]

    model_output = _optional_model(model, p, features, "audio")
    method, model_version = "acoustic_and_prosodic_heuristics", None
    if model_output:
        output, model_evidence = model_output
        classification = output["classification"]
        evidence.extend(model_evidence)
        limitations.extend(output.get("limitations", []))
        method, model_version, confidence = "ml", model.model_version, output.get("confidence")

    elapsed = (time.perf_counter() - start) * 1000
    return _result(
        classification,
        method=method,
        evidence=evidence,
        features=features,
        limitations=limitations,
        confidence=confidence,
        model_version=model_version,
        elapsed=elapsed,
    )


def analyze_video(path: str | Path, model: VideoDeepfakeModel | None = None) -> DetectorResult:
    """Analyze video for temporal inconsistencies, frame splicing, optical flow jitter, and visual artifacts."""
    start = time.perf_counter()
    p, data = _validate_file(path)
    evidence = []
    detected_indicators = []

    try:
        features = extract_video_features(p)
    except Exception as exc:
        features = {"byte_length": len(data), "sha256": hashlib.sha256(data).hexdigest(), "extraction_error": str(exc)}

    evidence.append({
        "indicator": "video_stream_properties",
        "type": "observed_file_property",
        "value": {
            "total_frames": features.get("total_frames"),
            "fps": features.get("fps"),
            "duration_seconds": features.get("duration_seconds"),
        },
    })

    prob_score = 0.04  # baseline benign

    ssim_drops = features.get("ssim_drop_count", 0)
    min_ssim = features.get("min_interframe_ssim", 1.0)
    optical_jitter = features.get("optical_flow_jitter", 0.0)
    lum_flicker = features.get("luminance_flicker_ratio", 0.0)
    key_ela = features.get("keyframe_ela_discrepancy", 1.0)
    key_fft = features.get("keyframe_fft_spike", 0.0)

    # 1. Temporal Continuity & Inter-Frame SSIM Drops
    if ssim_drops >= 1 or min_ssim < 0.85:
        prob_score += 0.45
        ind = "temporal_frame_discontinuity"
        evidence.append({"indicator": ind, "type": "temporal_consistency", "value": f"{ssim_drops} drops, min SSIM {min_ssim:.2f}"})
        detected_indicators.append("Significant frame-to-frame structural discontinuity (SSIM drop) indicating spliced or swapped frames.")

    # 2. Optical Flow Jitter & Motion Warping
    if optical_jitter >= 2.5:
        prob_score += 0.35
        ind = "optical_flow_jitter"
        evidence.append({"indicator": ind, "type": "motion_vectors", "value": f"jitter magnitude {optical_jitter:.2f}"})
        detected_indicators.append("Irregular optical flow velocity variance suggesting face boundary warping or temporal swimming.")

    # 3. Luminance / Lighting Flicker
    if lum_flicker >= 0.08:
        prob_score += 0.20
        ind = "luminance_temporal_flicker"
        evidence.append({"indicator": ind, "type": "illumination", "value": f"flicker ratio {lum_flicker:.3f}"})
        detected_indicators.append("Unnatural frame-to-frame exposure or color temperature flickering.")

    # 4. Keyframe Visual Splicing
    if key_ela >= 4.0 or key_fft >= 1.5:
        prob_score += 0.30
        ind = "keyframe_visual_anomaly"
        evidence.append({"indicator": ind, "type": "keyframe_artifacts", "value": f"ELA {key_ela:.1f}, FFT {key_fft:.2f}"})
        detected_indicators.append("Keyframes exhibit compression or generative frequency artifacts.")

    manip_prob = round(min(0.96, max(0.03, prob_score)), 4)
    auth_score = round(1.0 - manip_prob, 4)
    concern_level, classification = _determine_concern(manip_prob)
    confidence = round(min(0.95, 0.70 + 0.05 * len(detected_indicators)), 2)

    features.update({
        "authenticity_score": auth_score,
        "manipulation_probability": manip_prob,
        "confidence": confidence,
        "concern_level": concern_level,
        "detected_indicators": detected_indicators,
    })

    limitations = [
        EPISTEMIC_LIMITATION,
        "Video compression codecs (H.264/H.265/VP9) and packet loss can introduce temporal compression artifacts.",
    ]

    model_output = _optional_model(model, p, features, "video")
    method, model_version = "temporal_continuity_and_optical_flow", None
    if model_output:
        output, model_evidence = model_output
        classification = output["classification"]
        evidence.extend(model_evidence)
        limitations.extend(output.get("limitations", []))
        method, model_version, confidence = "ml", model.model_version, output.get("confidence")

    elapsed = (time.perf_counter() - start) * 1000
    return _result(
        classification,
        method=method,
        evidence=evidence,
        features=features,
        limitations=limitations,
        confidence=confidence,
        model_version=model_version,
        elapsed=elapsed,
    )

