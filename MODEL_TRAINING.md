# Model training

CYBERGUARD does not guarantee perfect detection. Accuracy depends on the threat sources, recording conditions, labels, and operating threshold represented in the data. Treat every result as a triage signal and keep human review in the loop.

## Train local voice, image, and video models

The multimedia trainer fits one separate, CPU-friendly feature model per modality. It uses CYBERGUARD's existing handcrafted audio/image/video features and scikit-learn; it does not download models, upload files, transcribe speech, or perform OCR. This is a reproducible baseline, not a universal deepfake detector or a substitute for a validated forensic model.

### 1. Prepare an authorized dataset

Keep original media and manifests outside the source repository, for example:

```text
C:\cyberguard-private-data\audio\
  clips\
  manifest.csv
C:\cyberguard-private-data\images\
  photos\
  manifest.csv
C:\cyberguard-private-data\video\
  clips\
  manifest.csv
```

Create a separate manifest for each modality with these columns:

```csv
file,label,group_id
clips/speaker_001_real.wav,authentic,speaker_001
clips/speaker_001_generated.wav,synthetic,speaker_001
clips/speaker_002_real.wav,authentic,speaker_002
clips/speaker_002_generated.wav,synthetic,speaker_002
```

Accepted labels are `authentic`/`real`/`human` and `synthetic`/`ai_generated`. For audio, `authentic` means an authorized human voice recording and `synthetic` means AI-generated speech. For images and video, label actual camera-origin material `authentic` and AI-generated material `synthetic`. Do not relabel ordinary edited media or a manipulated-but-not-generated clip as synthetic unless that is the explicitly intended target; origin and manipulation are different questions.

`group_id` identifies the person, speaker, original source recording, photo sequence, or video source that must stay together. If a generated sample is based on a real person/source, put both in the same group. The trainer keeps groups disjoint across train, validation, and test partitions, so the reported test metric is not inflated by near-identical content crossing the split. It rejects exact duplicate files, unsupported labels, missing files, and paths that escape the manifest directory.

Use only media you have the legal right and explicit informed consent to use for model training, especially identifiable voices and faces. Record each source's license, provenance, collection date, generator (when known), consent/authorization, and permitted purpose in your own dataset notes. Do not scrape private accounts, use confidential recordings, or commit raw media, manifests containing personal data, or trained artifacts to Git. The trainer reports a SHA-256 dataset fingerprint; it does not copy original files into the model output.

The minimum enforced by the trainer is 20 examples per class and eight distinct groups overall, and each held-out partition must contain both labels. These are minimum mechanics checks, not enough data to establish useful generalization. Prefer hundreds or thousands of independently sourced examples per class, multiple speakers/identities and devices, varied languages, microphones, codecs, noise, lighting, camera sources, and several current generation systems. Balance conditions between classes; do not let a codec, resolution, background, or generator identify the label by itself.

### 2. Install project dependencies and train

From the repository root, activate the project's virtual environment as described in [README.md](./README.md), then run one command per modality:

```powershell
python -m training.media --modality audio --manifest "C:\cyberguard-private-data\audio\manifest.csv" --output-dir models\media
python -m training.media --modality image --manifest "C:\cyberguard-private-data\images\manifest.csv" --output-dir models\media
python -m training.media --modality video --manifest "C:\cyberguard-private-data\video\manifest.csv" --output-dir models\media
```

Each run writes the selected artifact (`audio.joblib`, `image.joblib`, or `video.joblib`) and a matching `.registry.json` alongside it. Artifacts are local model outputs; do not commit them. The trainer selects a decision threshold on the validation partition only, then reports held-out test precision, recall, F1, false-positive rate, false-negative rate, and confusion matrix. Inspect the report before using the model. A bad test result means the model/data is not ready; do not keep adjusting the threshold against the test set.

### 3. Use a trained artifact

The dashboard automatically uses a model if its artifact is at `models\media\audio.joblib`, `models\media\image.joblib`, or `models\media\video.joblib`. Restart the local dashboard after replacing a model so its cached adapter reloads the artifact. The dashboard's detector status reports whether each modality model is available. Without an artifact, CYBERGUARD falls back to its existing conservative heuristic path.

The adapter reports no confidence. The model's synthetic-class score is explicitly recorded as an **uncalibrated score**, not as a probability. Predictions within a small margin of the validation threshold are `inconclusive`; that threshold and margin are safeguards, not guarantees of correctness.

## Evaluation and improving quality

1. **Define the exact target first.** Human-vs-generated voice, camera-vs-generated image, and camera-vs-generated video are not the same as detecting edits, impersonation, or malicious intent.
2. **Label from verified provenance.** Track source, generator/version where known, post-processing, recording conditions, consent, and label reviewer. Resolve uncertain examples rather than guessing.
3. **Prevent leakage.** Group all clips from a speaker, derived generations, frames from a source video, burst photos, and near-duplicates together. Never select thresholds or models based on the final test set.
4. **Measure the errors that matter.** Review each class's precision/recall, false-positive/negative rates and confusion matrix. Compare thresholds on validation data against an agreed false-positive budget. Test separately on new speakers, sources, devices, codecs, languages, and generator families.
5. **Calibrate before treating scores as probabilities.** These baselines are not calibrated and deliberately emit no confidence. If calibration is added, fit it using a separate calibration partition, verify reliability diagrams/Brier score and subgroup behavior, version the method, and retain a separate untouched test set.
6. **Keep a model card and rollback copy.** Record dataset and artifact hashes, permissions, split design, metrics, operating threshold, known limitations, subgroup results, and training command. Compare a candidate with the previous model before replacing it.
7. **Collect hard negatives and drift samples.** Include real recordings with compression, telephone bandwidth, denoising, music, varied speaking styles, poor lighting, animation, and real camera noise, as well as outputs from multiple unrelated generators. Avoid identity and generator shortcuts.

The current feature baseline can only learn patterns represented by its numeric features. In particular, image/video metadata and acoustic cues can be changed by benign recompression, editing, devices, or recording conditions. Real-world performance is unknown until measured on a representative, independently collected test set. No dataset or model downloaded from a third party is bundled by this project.

## Other detector models

- Email/phishing NLP already has a separate CSV training/evaluation workflow in `training/phishing.py`; see `python -m backend.cli --help` and the dataset preparation instructions in [README.md](./README.md).
- Login Isolation Forest training currently evaluates against generated synthetic login patterns only. Its reported metrics do not measure real account-takeover performance.
- URL, webpage, and security-rule checks are deterministic indicators, not models trained by `training.media`. Their findings are not proof of maliciousness.
