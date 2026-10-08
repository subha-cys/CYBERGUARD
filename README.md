# CYBERGUARD

CYBERGUARD is a local cybersecurity analysis dashboard and Python detection pipeline. It combines rule-based and ML signals into an explainable risk assessment for pasted email, URLs, websites, login events, and media files. Results are advisory; the app does not execute response actions or submit government complaints.

## Quick start

Requirements: Python 3.11 or later. The project is developed and tested from the repository root.

```bash
python -m venv .venv
# Windows PowerShell:
# .\.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m backend.web
```

Open <http://127.0.0.1:8765>. On Windows, `run.bat` can launch the local dashboard after the required phishing model is available. The dashboard binds to loopback only by default.

The phishing model and its training corpus are not distributed with this repository. See [dataset preparation](datasets/README.md) and `python -m backend.cli --help` to prepare an authorized dataset and train the model. Do not commit trained model files, raw datasets, or local SQLite databases.

## Project layout

```text
backend/       Dashboard server, CLI, analysis service, and pipeline
detectors/     Common contract and inference adapters for phishing, URLs, login, and media
features/      Versioned feature extraction shared where needed
training/      Offline model training and evaluation pipelines
datasets/      Dataset manifest, import tooling, and synthetic login generator
models/        Local serialized models (generated locally; ignored by source control)
fusion/        Independent-signal normalization and threat fusion
risk/          Transparent configurable risk policy
explainability/ Evidence-grounded structured explanation
response/      Advisory-only response recommendations
database/      Local SQLite incident store
tests/         Contract, feature, validation, and inference tests
frontend/      Local dashboard UI
docs/          Measured evaluation and complete detector demo outputs
```

## Phase 2 intelligence pipeline

Run `python -m backend.cli demo` to execute the CLI's synthetic scenarios through the available detectors and print the full input, detector outputs, evidence, fusion, risk, explanation, response advice, and incident result. The demonstration uses reserved documentation IP ranges and synthetic login identities; qualifying synthetic incidents are written to the local incident database. Do not run it against a production incident database. Use `--output-file` only with a new local output path if you also want to save the printed results.

Fusion uses categorical independent signals and keeps each detector confidence separate; it never averages confidence values. A phishing ML positive, rule indicators, and URL indicators remain distinct supporting signals. A benign/no-anomaly output is recorded as disagreement only when another detector in that threat family is positive. Rule/URL evidence without a positive NLP result is labeled `suspicious_phishing`. Login rules and Isolation Forest are fused as account-takeover signals. Unknown labels remain neutral.

Risk is computed from the versioned weights in [`risk/risk_policy.json`](risk/risk_policy.json): base threat points, evidence indicator points, 15 points when at least two detectors support the assessment, and asset sensitivity points. The sum is capped at 100; confidence is not a score input. Bands are low 0–24, medium 25–49, high 50–74, and critical 75–100. The incident threshold is 50. Incident actions and response recommendations are advisory; every recommendation requires approval and has automatic execution disabled. Explanation text is constructed from structured detector outputs, evidence, risk contributors, and policy actions, not generated from unconstrained model prose.

The **MULTIMEDIA MANIPULATION ASSESSMENT** module accepts image/audio/video files and emits common-contract results. Audio includes a no-dependency heuristic voice-origin label (`likely_ai_generated`, `likely_human`, or `inconclusive`) based on acoustic cues; it is not a validated model, reports no confidence, and is not proof of origin. A likely AI-generated voice is fused as `synthetic_voice`. The existing image/audio/video heuristic indicator score is not a probability, and heuristic paths report no confidence. Failed feature extraction returns `inconclusive`, rather than a benign-looking default. Locally trained image/audio/video models can be added through the group-aware workflow documented in [Model training](MODEL_TRAINING.md); without those artifacts, no trained media model is installed. See [multimedia assessment notes](detectors/MULTIMEDIA_ASSESSMENT.md) for supported formats and limitations.

Asset sensitivity is inferred locally after analysis from inspectable submitted text. Confirmed-looking secrets, direct identifiers, and card/financial/identified medical data raise the inferred level; otherwise it defaults to medium. The upload workflow does not run OCR or speech transcription, so an image or video containing sensitive text, or an audio recording containing sensitive spoken data, is not classified by its unseen contents. The inferred level and rationale are shown with each result and contribute to risk scoring where the threat policy applies.

For the dashboard email workflow, choose **Email** and paste the full email once (including `From`, `Subject`, and authentication headers when available). CyberGuard decodes standard MIME text parts, inspects visible message text, and checks both written URLs and HTTP(S) link destinations embedded in HTML. It extracts available sender/header fields, possible claimed roles and organizations, likely requested actions, attachment filenames, and URLs. Missing identity information is reported rather than guessed. Role, organization, and objective outputs are heuristic clues, not verified facts or proof of intent. Authentication results copied from a message are unverified claims unless they are known to come from a trusted receiving mail server. Existing API callers can continue to submit `{"type":"email","text":"..."}`; full pasted emails may use `{"type":"email","raw_message":"..."}` for automatic header and MIME extraction.

Detection cannot guarantee that every malicious email will be flagged. The bundled text model reports strong metrics on a random split of an older mixed-source corpus, but those metrics do not establish current or real-world performance; the corpus manifest explicitly notes potential source/near-duplicate leakage and lack of temporal evaluation. Better accuracy claims require a representative, recent, independently labeled temporal test set that includes benign business email and current phishing, with false-positive/false-negative rates reported at the intended alert threshold. URL checks are offline lexical checks and do not query live reputation or resolve destinations. Message structure follows [RFC 5322](https://www.rfc-editor.org/rfc/rfc5322.html) and Python's [email parsing API](https://docs.python.org/3/library/email.parser.html); authentication results are treated as unverified metadata, consistent with the trust-boundary caveats in [RFC 8601](https://www.rfc-editor.org/rfc/rfc8601.html) and the alignment semantics in [DMARC RFC 9989](https://www.rfc-editor.org/rfc/rfc9989.html).

## Local dashboard

Start the analyst dashboard with `python -m backend.web` and open `http://127.0.0.1:8765`. The browser interface calls the actual detector adapters, fusion/risk/explanation/response pipeline, and SQLite incident store. Demo scenarios are selected from the New analysis page; choosing one prefills an input and does not run analysis until the user clicks Analyze. Synthetic demo runs are excluded from dashboard totals and the incident queue. The dashboard also links to the official Indian Cyber Crime Reporting Portal and can prepare an editable complaint draft for a threat-qualified live analysis; filing remains a user action. Incident status changes are local case management only. See [frontend instructions](frontend/README.md).

Only real `/api/analyze` requests scoring at or above the incident threshold are saved to the dashboard incident queue. UI demo selections only prefill synthetic inputs; they are analyzed only after the user presses **Analyze**, and are excluded from persisted incidents and dashboard analysis totals. Each live incident records its `live_analysis` source and a limited input summary; raw message bodies are not retained there. Historical records without provenance are excluded from the live incident list.

The dashboard can prepare an editable complaint draft and links to the official [Indian Cyber Crime Reporting Portal](https://cybercrime.gov.in/Webform/Crime_AuthoLogin.aspx). It never submits complaints or sends message content or identity documents automatically. Review all generated details before filing.

## Chrome extension

Build the unpacked extension with `python extension/build_extension.py`, load `extension/build` from `chrome://extensions`, and enable website monitoring in its popup. The extension uses the existing loopback Python service and can optionally install that service as a Windows sign-in scheduled task. Monitoring is off until explicitly enabled, and Chrome must remain running while the device is awake. See [extension setup and runtime limits](extension/README.md).

## Data provenance and model limitations

Training requires an authorized CSV with `text,label` columns and `phishing` or `benign` labels. Small fixtures are only for tests and must not be reported as model performance. Do not mix datasets or evaluation splits when comparing models.

The recommended public dataset is the [Zenodo Phishing-Email-Detection-Dataset](https://doi.org/10.5281/zenodo.17314806), a CC BY 4.0 balanced release compiled from nine public corpora. Read its manifest and the source documentation before using or redistributing. The corpus is historical and merged-source random splits may overstate generalization.

## Train and evaluate

```powershell
.\.venv\Scripts\python.exe -m backend.cli train --csv datasets\phishing_email.csv --output models\phishing
.\.venv\Scripts\python.exe -m backend.cli analyze-email --model models\phishing\model.joblib --text "Your account needs verification"
.\.venv\Scripts\python.exe -m backend.cli analyze-email-rules --text "Your account needs verification" --sender "help@example.org" --url "http://192.0.2.44/verify"
.\.venv\Scripts\python.exe -m backend.cli analyze-url --url "https://example.org/login"
.\.venv\Scripts\python.exe -m backend.cli analyze-login --json-file datasets\demo_login.json
.\.venv\Scripts\python.exe -m backend.cli evaluate-login-ml --output models\login
.\.venv\Scripts\python.exe -m backend.cli analyze-login-ml --model models\login\model.joblib --json-file datasets\demo_login.json
.\.venv\Scripts\python.exe -m backend.cli analyze-media --type image --file path\to\authorized-media.png
.\.venv\Scripts\python.exe -m backend.cli demo --output-file docs\demo_outputs.json
```

Source conversion example (replace source column/label values after inspecting the source CSV):

```powershell
& .\.venv\Scripts\python.exe -m backend.cli prepare-dataset --input datasets\raw\Balanced_Dataset.csv --output datasets\phishing_email.csv --text-column body --label-column label --phishing-label 1.0 --benign-label 0.0
```

After setup, run tests with `python -m pytest`. Training splits data stratified into train/validation/test partitions with a fixed seed, compares TF-IDF Logistic Regression and Linear SVM using validation macro-F1, then evaluates the selected pipeline once on held-out test data. Metrics include accuracy, precision, recall, F1, confusion matrix, and class counts. A corpus too small to produce valid splits is rejected rather than reported with misleading metrics. Registry metadata records dataset hash, versions, timestamp, metrics, and limitations.

## Detection boundaries

Email ML uses text only; sender headers and security indicators are returned by a separate rule detector. URL extraction is lexical and never fetches URLs. Login has transparent rules plus a serialized Isolation Forest baseline evaluated on deliberately generated synthetic labels; its metrics do not imply real-world performance. Multimedia checks are limited to metadata/format/context signals unless an independently evaluated model adapter is supplied; they do not establish authenticity or deepfake status.

## License

The application code is licensed under the MIT License; see [LICENSE](LICENSE). External datasets, models, and media fixtures retain their own licenses and provenance requirements.
