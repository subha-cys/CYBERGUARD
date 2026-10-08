# MULTIMEDIA MANIPULATION ASSESSMENT

The detector accepts image, audio, and video file paths and returns the shared `DetectorResult` contract. It is a conservative format and context assessment. It is **not** a universal deepfake detector, and the repository does not bundle a validated image, audio, or video model.

Audio results include a separate `features.voice_origin` assessment: `likely_ai_generated`, `likely_human`, or `inconclusive`. Without a trained audio artifact this is a no-dependency acoustic heuristic reusing spectral, pitch, and voice micro-variation features. It reports no confidence score and is not validated on representative speech data; codec, bandwidth, noise reduction, speaking style, and health can affect its cues. Treat it as a triage hint only, never proof that a voice is AI-generated or human. Fusion raises the `synthetic_voice` category only for the `likely_ai_generated` label.

The heuristic `features.manipulation_indicator_score` is a hand-weighted indicator score, not a probability. Heuristic confidence and authenticity scores are returned as unavailable (`null`), not invented. If feature extraction fails, the classification is `inconclusive`. A trained modality model can replace the heuristic classification when installed at `models/media/{image,audio,video}.joblib`; the model's score remains explicitly uncalibrated and the adapter emits no confidence. See [model training](../MODEL_TRAINING.md).

## Current pipeline

1. Validate an existing regular file, size (1 byte to 100 MiB), and read a bounded snapshot.
2. Identify a supported format and parse conservative metadata.
3. Extract format properties. Images include dimensions, bit depth/color or JPEG quantization/metadata markers and byte-to-pixel ratio. WAV audio includes codec/container, channels, sample width/rate, duration, and bounded first-ten-second RMS. When `ffprobe` is present, other audio codecs and video streams get metadata parsing. When `ffmpeg` is present, video samples at most three frames (one per ten seconds, scaled to 640 pixels) for frame header properties.
4. Record available format/stream consistency observations. The default does not compare a speaker to a claimed identity or establish editing history. Audio/video synchronization is not validated.
5. Return `inconclusive` for readable media when evidence is insufficient, `unsupported` for unknown formats, or `suspicious` from an explicit contextual rule/model. Header anomalies and metadata are not proof of manipulation and do not by themselves raise a manipulation classification. No deepfake probability is produced.
The exact limitation `Manipulation cannot be determined from available evidence.` is included in default media results for UI display. `no_significant_indicators` means only that these limited checks did not find a notable indicator; it does not establish authenticity.

## Model adapters

Implement `ImageManipulationModel`, `AudioDeepfakeModel`, or `VideoDeepfakeModel` and pass the instance to the matching `analyze_*` function. Adapters must provide `model_version`, `evaluation_reference`, and a supported categorical result. A returned confidence is passed through only if the model supplies it; the adapter does not synthesize one. Before enabling an adapter, document dataset license/provenance, consent/authorization, group-safe evaluation split design, subgroup performance, calibration, operating threshold, and known limits. No public media corpus is downloaded or bundled by this module.

## Supported formats and runtime tools

Image headers: PNG, JPEG, GIF, BMP, WebP. Audio: WAV built in; additional decodable audio streams can be inspected when `ffprobe` is installed. Video: MP4/WebM signatures; stream metadata and limited frame sampling are optional via `ffprobe`/`ffmpeg`. Unknown/malformed formats return `unsupported` or `inconclusive`, never an authenticity claim. Optional command line tools run without a shell, with timeouts; frame output is kept in a temporary directory.

Only public, synthetic, or explicitly authorized media should be used for development. Do not submit private people's media without their authorization. No test dataset is included or used; synthetic byte fixtures may be used for parser tests.
# Live microphone voice checks

The Audio workspace can capture a default laptop microphone or any microphone exposed by the browser, including connected external microphones. It analyzes local rolling five-second WAV windows through `/api/live-voice`; those microphone windows are held in a temporary file during analysis, then deleted, and do not create incidents. The browser requests echo cancellation, noise suppression, and automatic gain control, when supported. Very quiet, clipped, speech-poor, and overlong windows are inconclusive instead of being assigned a forced origin label.

This is a live convenience path over the existing acoustic heuristic or an installed local audio model, not a validated call-forensics system. Browser noise suppression may help in loud spaces but cannot remove every background sound or guarantee accuracy. Use headphones or move closer to a directional microphone when possible, keep the speaker audible without clipping, and treat every result as advisory. A model's score is not shown as confidence.
