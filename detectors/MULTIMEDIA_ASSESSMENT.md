# MULTIMEDIA MANIPULATION ASSESSMENT

The detector accepts image, audio, and video file paths and returns the shared `DetectorResult` contract. It is a conservative format and context assessment. It is **not** a universal deepfake detector, and the repository has no validated image, audio, or video model installed.

## Current pipeline

1. Validate an existing regular file, size (1 byte to 100 MiB), and read a bounded snapshot.
2. Identify a supported format and parse conservative metadata.
3. Extract format properties. Images include dimensions, bit depth/color or JPEG quantization/metadata markers and byte-to-pixel ratio. WAV audio includes codec/container, channels, sample width/rate, duration, and bounded first-ten-second RMS. When `ffprobe` is present, other audio codecs and video streams get metadata parsing. When `ffmpeg` is present, video samples at most three frames (one per ten seconds, scaled to 640 pixels) for frame header properties.
4. Record available format/stream consistency observations. The default does not compare a speaker to a claimed identity or establish editing history. Audio/video synchronization is not validated.
5. Return `inconclusive` for readable media when evidence is insufficient, `unsupported` for unknown formats, or `suspicious` from an explicit contextual rule/model. Header anomalies and metadata are not proof of manipulation and do not by themselves raise a manipulation classification. No deepfake probability is produced.
The exact limitation `Manipulation cannot be determined from available evidence.` is included in default media results for UI display. `no_significant_indicators` means only that these limited checks did not find a notable indicator; it does not establish authenticity.

## Model adapters

Implement `ImageManipulationModel`, `AudioDeepfakeModel`, or `VideoDeepfakeModel` and pass the instance to the matching `analyze_*` function. Adapters must provide `model_version`, `evaluation_reference`, and a supported categorical result. A returned confidence is passed through only if the model supplies it; the adapter does not synthesize one. Before enabling an adapter, document dataset license/provenance, consent/authorization, evaluation split design, subgroup performance, calibration, operating threshold, and known limits. No public media corpus is downloaded or bundled by this module.

## Supported formats and runtime tools

Image headers: PNG, JPEG, GIF, BMP, WebP. Audio: WAV built in; additional decodable audio streams can be inspected when `ffprobe` is installed. Video: MP4/WebM signatures; stream metadata and limited frame sampling are optional via `ffprobe`/`ffmpeg`. Unknown/malformed formats return `unsupported` or `inconclusive`, never an authenticity claim. Optional command line tools run without a shell, with timeouts; frame output is kept in a temporary directory.

Only public, synthetic, or explicitly authorized media should be used for development. Do not submit private people's media without their authorization. No test dataset is included or used; synthetic byte fixtures may be used for parser tests.
