"""Audio authenticity and synthetic speech feature extraction."""
from __future__ import annotations

import io
import math
import wave
from pathlib import Path
from typing import Any

import numpy as np
import scipy.io.wavfile as wavfile

MAX_ANALYSIS_SECONDS = 10


def _decode_pcm(raw: bytes, sample_width: int) -> np.ndarray:
    if sample_width == 1:
        return (np.frombuffer(raw, dtype=np.uint8).astype(np.int16) - 128).astype(np.int8)
    if sample_width == 2:
        return np.frombuffer(raw, dtype=np.int16)
    if sample_width == 3:
        packed = np.frombuffer(raw, dtype=np.uint8)
        if packed.size % 3:
            raise ValueError("24-bit PCM stream contains a partial sample")
        samples = packed.reshape(-1, 3).astype(np.int32)
        decoded = samples[:, 0] | (samples[:, 1] << 8) | (samples[:, 2] << 16)
        decoded[decoded & 0x800000 != 0] -= 0x1000000
        return decoded << 8
    if sample_width == 4:
        return np.frombuffer(raw, dtype=np.int32)
    raise ValueError(f"unsupported WAV sample width: {sample_width} bytes")


def _load_audio_samples(audio_input: str | Path | bytes) -> tuple[np.ndarray, int]:
    """Load audio samples as mono float32 array normalized to [-1.0, 1.0] and sample rate."""
    if isinstance(audio_input, (str, Path)):
        p = Path(audio_input)
        try:
            sr, data = wavfile.read(str(p))
        except Exception:
            # Fallback wave reader
            with wave.open(str(p), "rb") as w:
                sr = w.getframerate()
                nframes = w.getnframes()
                nchannels = w.getnchannels()
                sampwidth = w.getsampwidth()
                raw = w.readframes(nframes)
                data = _decode_pcm(raw, sampwidth)
                if nchannels > 1:
                    data = data.reshape(-1, nchannels)
    elif isinstance(audio_input, bytes):
        try:
            sr, data = wavfile.read(io.BytesIO(audio_input))
        except Exception:
            with wave.open(io.BytesIO(audio_input), "rb") as w:
                sr = w.getframerate()
                nchannels = w.getnchannels()
                sampwidth = w.getsampwidth()
                raw = w.readframes(w.getnframes())
                data = _decode_pcm(raw, sampwidth)
                if nchannels > 1:
                    data = data.reshape(-1, nchannels)
    else:
        raise TypeError(f"Unsupported audio input type: {type(audio_input)}")

    if sr <= 0:
        raise ValueError("audio sample rate must be positive")
    if data.size == 0:
        raise ValueError("audio stream contains no samples")

    # Stereo to mono
    if data.ndim > 1:
        data = np.mean(data, axis=1)

    # Convert to float32 [-1.0, 1.0]
    if np.issubdtype(data.dtype, np.integer):
        if data.dtype == np.uint8:
            float_data = ((data.astype(np.float32) - 128.0) / 128.0).astype(np.float32)
        else:
            max_val = float(np.iinfo(data.dtype).max)
            float_data = (data / max_val).astype(np.float32)
    else:
        float_data = data.astype(np.float32)

    if not np.all(np.isfinite(float_data)):
        raise ValueError("audio stream contains non-finite samples")
    return np.clip(float_data, -1.0, 1.0), sr


def _compute_spectral_features(samples: np.ndarray, sr: int) -> dict[str, float]:
    """Compute spectral centroid, rolloff, and vocoder high-frequency brick-wall cutoff."""
    # STFT frame size 512, hop 256
    n_fft = 512
    hop = 256
    if len(samples) < n_fft:
        samples = np.pad(samples, (0, n_fft - len(samples)))

    # Frame windowing
    n_frames = (len(samples) - n_fft) // hop + 1
    frames = np.lib.stride_tricks.as_strided(
        samples,
        shape=(n_frames, n_fft),
        strides=(samples.strides[0] * hop, samples.strides[0]),
    )
    window = np.hanning(n_fft)
    spec = np.abs(np.fft.rfft(frames * window, axis=1))  # (n_frames, n_fft // 2 + 1)
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)

    power = spec ** 2
    frame_energy = np.sum(power, axis=1) + 1e-10

    # 1. Spectral Centroid
    centroids = np.sum(spec * freqs, axis=1) / (np.sum(spec, axis=1) + 1e-10)
    mean_centroid = float(np.mean(centroids))

    # 2. Spectral Rolloff (95% energy threshold)
    cumsum = np.cumsum(power, axis=1)
    rolloff_thresh = 0.95 * frame_energy[:, np.newaxis]
    rolloff_bins = np.argmax(cumsum >= rolloff_thresh, axis=1)
    rolloff_freqs = freqs[rolloff_bins]
    mean_rolloff = float(np.mean(rolloff_freqs))

    # 3. High-Frequency Brick-Wall Cutoff Detection
    # Neural vocoders often zero out or drastically truncate frequencies above 7.5kHz - 8kHz
    if sr >= 16000:
        cutoff_bin = np.searchsorted(freqs, 7600)
        hf_energy = np.mean(power[:, cutoff_bin:])
        total_energy = np.mean(power) + 1e-10
        hf_energy_ratio = float(hf_energy / total_energy)
    else:
        hf_energy_ratio = 0.05

    # 4. Spectral Flatness (geometric mean / arithmetic mean)
    log_power = np.log(spec + 1e-10)
    geom_mean = np.exp(np.mean(log_power, axis=1))
    arith_mean = np.mean(spec, axis=1) + 1e-10
    flatness = float(np.mean(geom_mean / arith_mean))

    return {
        "spectral_centroid_hz": round(mean_centroid, 1),
        "spectral_rolloff_hz": round(mean_rolloff, 1),
        "high_frequency_energy_ratio": round(hf_energy_ratio, 5),
        "spectral_flatness": round(flatness, 4),
    }


def _compute_pitch_and_microvariation(samples: np.ndarray, sr: int) -> dict[str, float]:
    """Estimate pitch (F0), period jitter, and amplitude shimmer."""
    frame_len = int(sr * 0.03)  # 30 ms frames
    hop_len = int(sr * 0.015)   # 15 ms hop
    min_lag = int(sr / 500)     # 500 Hz max pitch
    max_lag = int(sr / 60)      # 60 Hz min pitch

    pitches = []
    amplitudes = []

    for start in range(0, len(samples) - frame_len, hop_len):
        frame = samples[start:start + frame_len]
        energy = np.sum(frame ** 2)
        if energy < 0.001:
            continue

        # Autocorrelation
        autocorr = np.correlate(frame, frame, mode="full")
        autocorr = autocorr[len(autocorr) // 2:]

        if len(autocorr) > max_lag:
            windowed_corr = autocorr[min_lag:max_lag]
            peak_lag = min_lag + np.argmax(windowed_corr)
            peak_val = autocorr[peak_lag]
            # Check voicing threshold
            if peak_val > 0.3 * autocorr[0]:
                f0 = sr / peak_lag
                pitches.append(f0)
                amplitudes.append(float(np.max(np.abs(frame))))

    if len(pitches) >= 5:
        pitch_arr = np.array(pitches)
        amp_arr = np.array(amplitudes)
        f0_mean = float(np.mean(pitch_arr))
        f0_std = float(np.std(pitch_arr))

        # Jitter: cycle-to-cycle relative period variation
        periods = 1.0 / pitch_arr
        period_diffs = np.abs(np.diff(periods))
        jitter = float(np.mean(period_diffs) / (np.mean(periods) + 1e-8))

        # Shimmer: cycle-to-cycle relative amplitude variation
        amp_diffs = np.abs(np.diff(amp_arr))
        shimmer = float(np.mean(amp_diffs) / (np.mean(amp_arr) + 1e-8))
    else:
        f0_mean = 0.0
        f0_std = 0.0
        jitter = 0.005  # baseline
        shimmer = 0.03

    return {
        "mean_f0_hz": round(f0_mean, 1),
        "f0_std_hz": round(f0_std, 2),
        "vocal_jitter": round(jitter, 5),
        "vocal_shimmer": round(shimmer, 5),
    }


def _compute_silence_and_continuity(samples: np.ndarray, sr: int) -> dict[str, float]:
    """Measure digital silence drops and background noise consistency."""
    frame_size = int(sr * 0.02)  # 20 ms
    n_frames = len(samples) // frame_size
    if n_frames == 0:
        return {"digital_silence_fraction": 0.0, "zero_crossing_rate": 0.0}

    frame_energies = [np.mean(samples[i * frame_size:(i + 1) * frame_size] ** 2) for i in range(n_frames)]
    # Digital silence: energy < 1e-7 (essentially exact zero, common in concatenated TTS)
    digital_silence_count = sum(1 for e in frame_energies if e < 1e-7)
    digital_silence_fraction = float(digital_silence_count / n_frames)

    # Zero Crossing Rate
    zcr = float(np.mean(np.abs(np.diff(np.signbit(samples)))))

    return {
        "digital_silence_fraction": round(digital_silence_fraction, 4),
        "zero_crossing_rate": round(zcr, 4),
    }


def extract_audio_features(audio_input: str | Path | bytes) -> dict[str, Any]:
    """Extract comprehensive authenticity indicators from audio."""
    samples, sr = _load_audio_samples(audio_input)
    source_sample_count = len(samples)
    duration = round(source_sample_count / sr, 3)
    max_samples = sr * MAX_ANALYSIS_SECONDS
    if source_sample_count > max_samples:
        samples = samples[:max_samples]
    analyzed_duration = round(len(samples) / sr, 3)

    spectral_res = _compute_spectral_features(samples, sr)
    pitch_res = _compute_pitch_and_microvariation(samples, sr)
    silence_res = _compute_silence_and_continuity(samples, sr)

    return {
        "sample_rate_hz": sr,
        "duration_seconds": duration,
        "analyzed_duration_seconds": analyzed_duration,
        "analysis_truncated": source_sample_count > len(samples),
        "sample_count": len(samples),
        **spectral_res,
        **pitch_res,
        **silence_res,
    }
