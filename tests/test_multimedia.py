"""Comprehensive unit and integration tests for Deepfake & Multimedia Authenticity Detection."""
import pytest
from pathlib import Path

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
from detectors.multimedia import analyze_image, analyze_audio, analyze_video
from features.multimedia_image import extract_image_features
from features.multimedia_audio import extract_audio_features
from features.multimedia_video import extract_video_features
from backend.service import run_demo, analyze_request


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
    assert norm_res["features"]["authenticity_score"] > 0.85
    assert norm_res["features"]["manipulation_probability"] < 0.15

    manip_res = analyze_image(manip_path).to_dict()
    assert manip_res["features"]["concern_level"] == "HIGH CONCERN"
    assert manip_res["features"]["authenticity_score"] < 0.20
    assert manip_res["features"]["manipulation_probability"] > 0.80
    assert len(manip_res["features"]["detected_indicators"]) >= 2


def test_audio_feature_extraction_and_detection():
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
    assert norm_res["features"]["authenticity_score"] > 0.85

    synth_res = analyze_audio(synth_path).to_dict()
    assert synth_res["features"]["concern_level"] == "HIGH CONCERN"
    assert synth_res["features"]["authenticity_score"] < 0.20
    assert synth_res["features"]["manipulation_probability"] > 0.80
    assert len(synth_res["features"]["detected_indicators"]) >= 2


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
    assert norm_res["features"]["authenticity_score"] > 0.85

    manip_res = analyze_video(manip_path).to_dict()
    assert manip_res["features"]["concern_level"] == "HIGH CONCERN"
    assert manip_res["features"]["authenticity_score"] < 0.25
    assert manip_res["features"]["manipulation_probability"] > 0.70


@pytest.mark.parametrize("demo_id,expected_concern,expected_threat,min_risk,max_risk", [
    ("normal_image", "LOW CONCERN", "undetermined", 0, 24),
    ("synthetic_manipulated_image", "HIGH CONCERN", "multimedia_manipulation", 75, 100),
    ("normal_audio", "LOW CONCERN", "undetermined", 0, 24),
    ("synthetic_audio", "HIGH CONCERN", "multimedia_manipulation", 75, 100),
    ("normal_video", "LOW CONCERN", "undetermined", 0, 24),
    ("manipulated_video", "HIGH CONCERN", "multimedia_manipulation", 75, 100),
])
def test_all_six_synthetic_demonstration_cases(demo_id, expected_concern, expected_threat, min_risk, max_risk):
    result = run_demo(demo_id)
    assert result["concern_level"] == expected_concern
    assert result["threat_category"] == expected_threat
    assert min_risk <= result["risk_score"] <= max_risk
    assert isinstance(result["authenticity_score"], float)
    assert isinstance(result["manipulation_probability"], float)
    assert isinstance(result["recommended_action"], list)
    assert len(result["recommended_action"]) > 0
