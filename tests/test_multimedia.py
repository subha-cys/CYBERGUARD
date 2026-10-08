"""Comprehensive unit and integration tests for Deepfake & Multimedia Authenticity Detection."""
import io
import base64
import pytest
from pathlib import Path
import wave

from config.multimedia_config import check_system_capabilities, get_multimedia_config, update_multimedia_config
from datasets.media_fixtures import (
    create_normal_image_fixture,
    create_manipulated_image_fixture,
    create_normal_audio_fixture,
    create_synthetic_audio_fixture,
    create_normal_video_fixture,
    create_manipulated_video_fixture,
    ensure_all_fixtures,
)
from detectors.multimedia import _assess_voice_origin, analyze_image, analyze_audio, analyze_video
from features.multimedia_image import extract_image_features
from features.multimedia_audio import _decode_pcm, extract_audio_features
from features.multimedia_video import extract_video_features
from backend.service import analyze_live_voice, analyze_request, demo_fixture_data
from fusion.engine import fuse


def test_system_capabilities_inspection():
    caps = check_system_capabilities()
    assert "opencv_available" in caps
    assert "pillow_available" in caps
    assert "scipy_available" in caps
    assert "ffmpeg_available" in caps
    assert caps["pillow_available"] is True
    assert caps["scipy_available"] is True
    assert caps["opencv_available"] is True


def test_multimedia_config_system():
    cfg = get_multimedia_config()
    assert "model_mode" in cfg
    assert cfg["model_mode"] in {"lightweight", "advanced"}

    # Test update
    updated = update_multimedia_config({"model_mode": "advanced"})
    assert updated["model_mode"] == "advanced"
    # Revert to lightweight
    reverted = update_multimedia_config({"model_mode": "lightweight"})
    assert reverted["model_mode"] == "lightweight"


def test_image_feature_extraction_and_detection():
    norm_path = create_normal_image_fixture()
    manip_path = create_manipulated_image_fixture()

    norm_feat = extract_image_features(norm_path)
    manip_feat = extract_image_features(manip_path)

    # Normal image has low ELA discrepancy and low FFT peak prominence
    assert norm_feat["ela_patch_discrepancy_ratio"] < 3.0
    assert norm_feat["fft_peak_prominence"] < 80.0

    # Manipulated image has high ELA discrepancy and high FFT peak prominence
    assert manip_feat["ela_patch_discrepancy_ratio"] > 10.0
    assert manip_feat["fft_peak_prominence"] > 100.0

    # Test detector outputs
    norm_res = analyze_image(norm_path).to_dict()
    assert norm_res["features"]["concern_level"] == "LOW CONCERN"
    assert norm_res["features"]["authenticity_score"] is None
    assert norm_res["features"]["manipulation_probability"] is None
    assert 0 <= norm_res["features"]["manipulation_indicator_score"] <= 1
    assert norm_res["confidence"] is None

    manip_res = analyze_image(manip_path).to_dict()
    assert manip_res["features"]["concern_level"] == "HIGH CONCERN"
    assert manip_res["features"]["authenticity_score"] is None
    assert manip_res["features"]["manipulation_probability"] is None
    assert manip_res["features"]["manipulation_indicator_score"] >= 0.70
    assert len(manip_res["features"]["detected_indicators"]) >= 2


def test_boundary_seam_contributes_to_uncalibrated_indicator_score(monkeypatch):
    path = create_normal_image_fixture()
    monkeypatch.setattr(
        "detectors.multimedia.extract_image_features",
        lambda _: {
            "ela_patch_discrepancy_ratio": 3.0,
            "fft_peak_prominence": 1.0,
            "fft_high_freq_spike": 0.0,
            "noise_variance_quadrant_ratio": 1.0,
            "edge_contrast_ratio": 20.0,
        },
    )
    result = analyze_image(path).to_dict()
    assert result["features"]["manipulation_indicator_score"] == 0.44


def test_audio_feature_extraction_and_detection():
    assert _assess_voice_origin({}, [])["classification"] == "inconclusive"

    norm_path = create_normal_audio_fixture()
    synth_path = create_synthetic_audio_fixture()

    norm_feat = extract_audio_features(norm_path)
    synth_feat = extract_audio_features(synth_path)

    # Normal audio has organic vocal jitter
    assert norm_feat["vocal_jitter"] > 0.002
    assert norm_feat["high_frequency_energy_ratio"] > 0.0001

    # Synthetic audio has sharp vocoder brick-wall cutoff and rigid micro-jitter
    assert synth_feat["vocal_jitter"] < 0.001
    assert synth_feat["high_frequency_energy_ratio"] < 0.00005
    assert synth_feat["digital_silence_fraction"] > 0.05

    # Test detector outputs
    norm_res = analyze_audio(norm_path).to_dict()
    assert norm_res["features"]["concern_level"] == "LOW CONCERN"
    assert norm_res["features"]["authenticity_score"] is None
    assert norm_res["features"]["manipulation_probability"] is None
    assert norm_res["confidence"] is None
    assert norm_res["features"]["voice_origin"]["classification"] == "likely_human"
    assert norm_res["features"]["voice_origin"]["confidence"] is None
    human_fusion = fuse([norm_res])
    assert human_fusion["threat"] == "undetermined"
    assert human_fusion["detector_results"][0]["voice_origin_signal"] == "conflict"

    synth_res = analyze_audio(synth_path).to_dict()
    assert synth_res["features"]["concern_level"] == "HIGH CONCERN"
    assert synth_res["features"]["authenticity_score"] is None
    assert synth_res["features"]["manipulation_probability"] is None
    assert synth_res["features"]["manipulation_indicator_score"] >= 0.70
    assert len(synth_res["features"]["detected_indicators"]) >= 2
    assert synth_res["features"]["voice_origin"]["classification"] == "likely_ai_generated"
    assert synth_res["features"]["voice_origin"]["confidence"] is None

    fused = fuse([synth_res])
    assert fused["threat"] == "synthetic_voice"
    assert fused["voice_origin"]["classification"] == "likely_ai_generated"


def test_long_audio_analysis_is_bounded_to_ten_seconds():
    sample_rate = 16_000
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(b"\x00\x00" * (sample_rate * 11))

    features = extract_audio_features(buffer.getvalue())
    assert features["duration_seconds"] == 11.0
    assert features["analyzed_duration_seconds"] == 10.0
    assert features["analysis_truncated"] is True
    assert features["sample_count"] == sample_rate * 10


def test_live_voice_rejects_silence_as_inconclusive_without_confidence():
    sample_rate = 16_000
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(b"\x00\x00" * (sample_rate * 5))

    result = analyze_live_voice({"content_base64": base64.b64encode(buffer.getvalue()).decode("ascii")})
    assert result["classification"] == "inconclusive"
    assert result["voice_origin"]["classification"] == "inconclusive"
    assert result["confidence"] is None
    assert result["audio_quality"]["usable"] is False
    assert result["audio_quality"]["warnings"]


def test_live_voice_accepts_a_speech_like_window_and_reports_audio_quality():
    import numpy as np

    sample_rate = 16_000
    samples = (np.sin(2 * np.pi * 180 * np.arange(sample_rate * 5) / sample_rate) * 10_000).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(samples.tobytes())

    result = analyze_live_voice({"content_base64": base64.b64encode(buffer.getvalue()).decode("ascii")})
    assert result["classification"] in {"likely_human", "likely_ai_generated", "inconclusive"}
    assert result["audio_quality"]["duration_seconds"] == 5.0
    assert result["audio_quality"]["usable"] is True
    assert result["confidence"] is None


def test_live_voice_clipping_forces_inconclusive():
    sample_rate = 16_000
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(b"\xff\x7f" * (sample_rate * 5))

    result = analyze_live_voice({"content_base64": base64.b64encode(buffer.getvalue()).decode("ascii")})
    assert result["classification"] == "inconclusive"
    assert result["audio_quality"]["usable"] is False
    assert any("clipping" in warning for warning in result["audio_quality"]["warnings"])


def test_live_voice_rejects_invalid_base64():
    with pytest.raises(ValueError, match="valid base64"):
        analyze_live_voice({"content_base64": "not base64!"})


def test_24_bit_pcm_is_sign_extended_and_scaled():
    pcm = bytes((0x00, 0x00, 0x80, 0xFF, 0xFF, 0x7F))
    decoded = _decode_pcm(pcm, 3)
    assert decoded.tolist() == [-(1 << 31), (1 << 31) - 256]


def test_media_feature_extraction_failures_are_inconclusive(tmp_path):
    bad_audio = tmp_path / "broken.wav"
    bad_audio.write_bytes(b"not an audio file")
    audio_result = analyze_audio(bad_audio).to_dict()
    assert audio_result["classification"] == "inconclusive"
    assert audio_result["confidence"] is None
    assert audio_result["features"]["analysis_status"] == "inconclusive"
    assert audio_result["evidence"][0]["indicator"] == "feature_extraction_failed"
    request_result = analyze_request({"type": "audio", "path": str(bad_audio)}, persist_incident=False)
    assert request_result["concern_level"] is None
    assert request_result["fusion"]["detector_results"][0]["classification"] == "inconclusive"

    bad_video = tmp_path / "broken.avi"
    bad_video.write_bytes(b"not a video file")
    video_result = analyze_video(bad_video).to_dict()
    assert video_result["classification"] == "inconclusive"
    assert video_result["confidence"] is None


def test_video_feature_extraction_and_detection():
    norm_path = create_normal_video_fixture()
    manip_path = create_manipulated_video_fixture()

    norm_feat = extract_video_features(norm_path)
    manip_feat = extract_video_features(manip_path)

    # Normal video has zero SSIM drops
    assert norm_feat["ssim_drop_count"] == 0
    assert norm_feat["mean_interframe_ssim"] > 0.90

    # Manipulated video has SSIM drops and lower min SSIM
    assert manip_feat["ssim_drop_count"] >= 1
    assert manip_feat["min_interframe_ssim"] < 0.88

    # Test detector outputs
    norm_res = analyze_video(norm_path).to_dict()
    assert norm_res["features"]["concern_level"] == "LOW CONCERN"
    assert norm_res["features"]["authenticity_score"] is None
    assert norm_res["features"]["manipulation_probability"] is None
    assert norm_res["confidence"] is None

    manip_res = analyze_video(manip_path).to_dict()
    assert manip_res["features"]["concern_level"] == "HIGH CONCERN"
    assert manip_res["features"]["authenticity_score"] is None
    assert manip_res["features"]["manipulation_probability"] is None
    assert manip_res["features"]["manipulation_indicator_score"] >= 0.70


@pytest.mark.parametrize("demo_id,expected_concern,expected_threat,min_risk,max_risk", [
    ("normal_image", "LOW CONCERN", "undetermined", 0, 24),
    ("synthetic_manipulated_image", "HIGH CONCERN", "multimedia_manipulation", 75, 100),
    ("normal_audio", "LOW CONCERN", "undetermined", 0, 24),
    ("synthetic_audio", "HIGH CONCERN", "synthetic_voice", 75, 100),
    ("normal_video", "LOW CONCERN", "undetermined", 0, 24),
    ("manipulated_video", "HIGH CONCERN", "multimedia_manipulation", 75, 100),
])
def test_all_six_synthetic_demonstration_cases(demo_id, expected_concern, expected_threat, min_risk, max_risk):
    modality = "image" if "image" in demo_id else "audio" if "audio" in demo_id else "video"
    result = analyze_request({
        "type": modality,
        "synthetic_demo": True,
        "demo_id": demo_id,
        **demo_fixture_data(demo_id),
    }, persist_incident=False)
    assert result["concern_level"] == expected_concern
    assert result["threat_category"] == expected_threat
    if demo_id == "normal_audio":
        assert result["voice_origin"]["classification"] == "likely_human"
    elif demo_id == "synthetic_audio":
        assert result["voice_origin"]["classification"] == "likely_ai_generated"
    assert min_risk <= result["risk_score"] <= max_risk
    if demo_id in {"normal_image", "synthetic_manipulated_image", "normal_audio",
                   "synthetic_audio", "normal_video", "manipulated_video"}:
        assert result["authenticity_score"] is None
        assert result["manipulation_probability"] is None
        assert isinstance(result["manipulation_indicator_score"], float)
    assert isinstance(result["recommended_action"], list)
    assert len(result["recommended_action"]) > 0
