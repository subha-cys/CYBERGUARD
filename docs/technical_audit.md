# CYBERGUARD Technical Audit

**Audit date:** 2026-09-25  
**Scope:** repository code, installed model artifacts/registries, dashboard/API, tests, and live loopback behavior. This is a prototype audit, not a penetration test or independent model validation. No implementation changes were made during the audit.

## A. Architecture status

The end-to-end path exists and is exercised: request adapter(s) → common detector results → `fusion.engine.fuse` → `RiskEngine.assess` → advisory `response.recommend` → structured `explainability.explain` → optional SQLite incident creation at score ≥50. The dashboard service invokes these components; the final threat label is computed from detector classifications and fixed category/precedence rules, not a scenario-specific constant.

The fusion taxonomy and precedence are hand-coded. `account_takeover` takes precedence over phishing, which takes precedence over identity context, then media manipulation. All detector evidence is retained, but only one top-level threat is returned. This is a deterministic rules-based fusion layer, not a learned fusion model.

`alert` means “incident record created.” There is no external alert delivery, SIEM integration, notification, or escalation workflow. Every response recommendation is advisory and `automatic_execution` is false.

## B. AI/ML status

| Component | Model and data | Features and measured metrics | Inference, confidence, reproducibility, limits |
|---|---|---|---|
| Phishing text | TF-IDF + LinearSVC, version `phishing-tfidf-linear-1.0.0`. Trained on Zenodo Phishing-Email-Detection-Dataset v2, CC BY 4.0; normalized counts: 98,085 positive (source combines phishing, spam, scam) and 95,619 benign. | Word unigrams/bigrams, `min_df=2`, max 50,000 features. Stratified 135,592/29,056/29,056 train/validation/test. Held-out: accuracy .9852, macro precision .9853, recall .9851, F1 .9852; confusion matrix `[[14071,272],[158,14555]]`. | The serialized model is loaded and called by `PhishingNLPDetector` in actual inference. Current LinearSVC confidence is null; its score is not a probability. Fixed split/model seeds, dataset hashes, and registry support reproduction, but package/library versions and artifact hashes are not pinned in the registry. Metrics are random-split corpus metrics, not current operational performance; no temporal or external holdout. |
| Login anomaly | StandardScaler + IsolationForest, 200 trees, contamination .20, version `login-iforest-synthetic-1.0.0`. Seeded synthetic events only; 1,000 rows, seed 17; 300 held-out events. | UTC hour, failed-attempt count, successful-login bit. Precision .5455, recall 1.0, F1 .7059; matrix `[[190,50],[0,60]]` (50 false positives among 240 normal events). | Serialized model is called during login inference. Confidence is null; the decision-function score is exposed only as a feature. Reproducible from generator and seeds. Synthetic patterns are deliberately separable and do not establish account-takeover performance. IP, country, and device do not enter the model features. |
| URL lexical detector | No ML model. Deterministic parser/rules. | Length, subdomains, token presence, IP literal, encoding, entropy, path/query, `@`, and HTTPS flag. No model metrics. | Runs at inference but never resolves or fetches the URL. Indicators do not prove maliciousness and there is no reputation, redirect, certificate, or domain-age check. Do not call this AI. |
| Email/login security rules | No ML model. Regex and event rules. | Urgency, credential/financial request, impersonation language, attachment wording, URL presence, domain mismatch; login hour/failures/success rules. No model metrics. | Actual rule detectors run in inference; output is categorical evidence with null confidence. They are security heuristics, not AI. |
| Multimedia | No image, audio, or video ML model is installed or evaluated. | Image headers/dimensions/properties; WAV metadata and first-ten-second RMS for 8-/16-bit data; optional ffprobe/ffmpeg code. Identity context is a separate rule function. | The current host has neither ffprobe nor ffmpeg, so non-WAV metadata parsing and video frame sampling are unavailable here. No manipulation or synthetic-speech detection is performed. Context rules can flag risk factors; they cannot validate an identity or a deepfake. The model adapter interfaces only require a non-empty evaluation-reference string; they do not independently verify validation/calibration. |

The old docs identify the correct phishing metrics and data limits, but refer to obsolete `backend.training.*` / `backend.datasets.*` module paths. The current packages are top-level `training` and `datasets`.

## C. Cybersecurity status

| Check | Finding |
|---|---|
| Suspicious URL / SSRF | URL analysis is lexical only; no request, DNS lookup, redirect follow, or URL visit occurs. This is a meaningful SSRF protection and should remain invariant. There is no live reputation verdict. |
| Upload validation | Dashboard caps decoded media at 100 MiB and request bodies at 140 MiB; paths are generated temporary files and removed in `finally`. The detector checks file size/signatures and returns unsupported/inconclusive for unrecognized inputs. It does not fully decode/validate all image structures. Base64 JSON is buffered and copied in memory; request streaming and per-client quotas are absent. |
| Malicious media | The current runtime has no ffmpeg/ffprobe. If enabled, uploaded files are parsed by native media binaries with timeouts and `shell=False`, but `file` protocol is allowed and parser vulnerabilities/resource exhaustion remain in scope. Process memory/output is not bounded. Test only with authorized media. |
| API exposure/auth | `backend.web` binds to loopback by default and rejects non-loopback bind names. It has no user authentication, authorization, TLS, rate limits, concurrency cap, or CSP/security headers. Safe only as a local prototype; do not expose through a LAN, tunnel, reverse proxy, or shared host. |
| Input sanitization | URL/login/media size and login schema are checked. Malformed JSON shape and email optional-field types are not validated consistently: manual probes returned HTTP 500 for a top-level JSON array and for an integer email URL. Unexpected exceptions are returned as raw error text. |
| Path traversal | Media input names are not used as filesystem paths (only a suffix is copied into a generated temp name); SQLite calls are parameterized. A URL-encoded traversal probe against static serving returned 404. No automated traversal regression test exists. |
| Command injection | ffmpeg/ffprobe use fixed argument arrays and `subprocess.run` without a shell. This avoids shell injection; it does not make complex media parsers safe. |
| Arbitrary code execution / supply chain | `joblib.load` deserializes pickle-based model artifacts. If a local model artifact is replaced by an attacker-controlled file, loading it can execute code as the dashboard process. There is no signed artifact/hash verification at model load. |
| Prompt injection | No LLM or prompt-based component is used. Submitted email text is passed to a vectorizer and deterministic rules, so prompt injection is not an applicable execution path in this build. |
| Secrets | No API credentials or service secrets are required or present in this local app. There is no secrets-management facility; add one before external integrations. |
| Logging / audit trail | HTTP access logs are suppressed; analysis content is not intentionally logged. This reduces content exposure but removes access/security audit visibility. Incident creation stores analysis outputs, but status changes overwrite status without actor, timestamp, reason, or append-only transition history. |
| Database | SQLite with parameterized statements and OS filesystem permissions; no application authentication, encryption at rest, backup policy, retention, or DB integrity monitoring. Submitted message body is not saved to the incident row; evidence/output is. |
| Automatic response | No destructive action is executed. Response actions require analyst approval and have `automatic_execution=false`. Incident status changes are the only mutating API action. |

## D. Fusion audit

**PASS with scope limitation.** `backend.pipeline.analyze` passes detector result dictionaries to fusion, then risk. Actual HTTP demos confirm the chain. Threat labels depend on the detector output classes and support/disagreement rules. Confidence values are preserved individually and never averaged. The detector/category mapping, supported class names, and precedence are hard-coded policy logic; unknown detector labels remain neutral. Multi-threat inputs retain categories/evidence but return only one primary `threat`, which can hide co-occurring categories in summary displays.

## E. Risk audit

Risk is separate from model confidence, deterministic for fixed detector outputs, configurable in `risk/risk_policy.json`, capped at 100, and exposes each contributor. Bands are low 0–24, medium 25–49, high 50–74, critical 75–100; incident threshold is 50. The policy does not validate every weight/type/range invariant, only basic band continuity and threshold bounds.

**Scoring concern:** evidence weights are collected from the flattened evidence list across all detector results without checking that the evidence came from a supporting detector or positive signal. A conflicting or unrelated detector can therefore contribute a positive risk weight. This is a correctness weakness when detectors disagree and should be fixed before operational use. URL support also contributes the generic `suspicious_url` weight whenever the URL detector is positive, regardless of which lexical indicator triggered it.

Observed scenario scores are reproducible from recorded evidence and policy: phishing 50, phishing+URL 92, synthetic login anomaly 80. These are policy scores, not calibrated probabilities or estimates of compromise likelihood.

## F. Explainability audit

The explanation builder uses a fixed template keyed by fused threat, detector classifications/versions, fusion evidence, risk contributors, limitations, and recommended action IDs. It does not generate free-form LLM prose. Reported evidence items can be traced to the flattened fusion evidence; “why” statements are based on normalized detector signals. This is substantially evidence-grounded.

Limitations: explanations are short templates, not causal explanations of model decisions; the LinearSVC has no token-level attribution. The current risk evidence/support mismatch can make a score contributor appear valid even if a detector did not support the fused threat. Cross-category precedence can also yield one top-level explanation while other positive categories remain in `fusion.categories`.

## G. Multimedia audit

The present implementation is **metadata/format inspection plus separate identity/context rules**, not deepfake detection. Images are header-parsed, not semantically decoded. WAV receives basic metadata and normalized RMS, not voice-authenticity analysis. Video currently only recognizes MP4/WebM signatures; no ffprobe/ffmpeg is installed on the audited host, so no frames or audio/video consistency are analyzed. The multimedia result is therefore normally `inconclusive` or `unsupported` with null confidence and the explicit limitation “Manipulation cannot be determined from available evidence.”

The identity context function is a hand-written security rule. Its synthetic demo shows an inconclusive synthetic PNG and a separate identity-context rule result. It does not establish media alteration, identify a depicted person, or validate the claimed identity.

## H. Performance measurements

Measured on this Windows workspace, Python 3.14.7, scikit-learn 1.9.1, local serialized models, loopback dashboard. These are small single-process measurements, not production capacity claims.

| Measurement | Observed |
|---|---:|
| Phishing model load (after importing detector module) | 1,251 ms |
| Login model load (same process) | 97 ms |
| Warm phishing detector, 50 measured calls | median 1.018 ms; p95 1.287 ms |
| Warm login Isolation Forest detector, 50 measured calls | median 25.461 ms; p95 25.959 ms |
| URL-only API, 30 sequential loopback requests including SQLite write | median 18.271 ms; p95 25.329 ms; 62.45 req/s sequential |
| Python working set after detector imports | 42.75 MiB |
| Working set after loading phishing model | 135.78 MiB |
| Working set after both models | 143.80 MiB; peak 145.79 MiB |

The API measurement excludes concurrency and large uploads. Login latency includes adapter validation/feature preparation. Cold model loading is lazy and occurs on the first applicable analysis request. Memory uses process working-set sampling; it is not a per-request peak under load. No concurrent throughput or 100-MiB upload memory benchmark was run.

## I. Testing results

**Automated:** `python -m pytest -q` → **18 passed in 1.60 s**. Collection: 13 detector/features/input tests, 2 pipeline/risk/incident tests, 3 training/data tests. Node JavaScript syntax check and Python web/service compilation also passed.

**Manual live API checks:** health/dashboard/static assets returned 200; four demo endpoints returned real detector/fusion results; email, URL, login, PNG upload, WAV upload, and MP4-signature upload paths were exercised. Incident transitions `acknowledged → investigating → resolved → open` succeeded after correcting the route during dashboard implementation. Oversized declared body and URL-encoded traversal probe were rejected (400 and 404 respectively).

**Malformed probes:** malformed JSON, invalid URL, malformed login, bad base64, oversized email were rejected with 400. Unsupported media returned an `unsupported` detector result (200), which is appropriate for a structured assessment. Two malformed shapes exposed bugs: top-level JSON array → 500 (`list has no attribute get`); email `url: 123` → 500 (type error in URL parsing). No automated API tests currently encode these outcomes.

**Coverage gaps:** no automated web/API tests; no dedicated multimedia parser tests; no direct unit tests for fusion edge cases or response policy; only minimal risk validation; no concurrency/load test; no golden regression snapshots. `test_six_scenario_logic_and_incidents` uses synthetic detector dictionaries and does not exercise the complete actual-detector stack. Live demo checks supplement but do not replace automated integration tests.

**CLI integration bug found:** `python -m backend.cli analyze-media --type image --file <valid image>` returned `{"error": "'Namespace' object has no attribute 'output'}` and exit code 2. The `analyze-media` branch assigns a result, then falls into the later command dispatch `else`, which tries to read the training command's `args.output`. The dashboard service calls the multimedia functions directly and works; the documented CLI command does not.

## J. Requirement traceability

| Requirement | Implementation | Evidence | Test/check | Status |
|---|---|---|---|---|
| Phishing AI model actually used | `detectors/phishing.py`, model artifact | Registry says LinearSVC; live phishing demo classification `phishing` | Model roundtrip + live demo | PASS |
| Phishing confidence honest | Confidence null for LinearSVC | Live output null; registry limitation | Detector contract + live output | PASS |
| Login ML model and real data | `training/login.py`, `detectors/login_ml.py` | Synthetic test metrics; live IF signal | Synthetic roundtrip + live demo | PARTIAL |
| URL threat detection | `detectors/url.py`, `features/url.py` | Lexical flags and limitations; no fetch | URL feature tests + API URL input | PARTIAL |
| Multiple detectors → fusion → risk | `backend/pipeline.py`, fusion/risk engines | Exact captured outputs below | Fixture pipeline tests + live demos | PASS |
| Final classification data-dependent | `fusion/engine.py` categorical signal mapping | Live model/rule outputs differ by scenario | Pipeline tests + live outputs | PASS |
| Risk configurable and explainable | `risk/risk_policy.json`, `risk/engine.py` | Contributor lists and thresholds | One policy validation test + demo scores | PARTIAL |
| Confidence distinct from risk | risk ignores confidence | `model_confidence_is_not_risk`; confidence null in demos | Pipeline test + captured outputs | PASS |
| Evidence-grounded explanation | `explainability/engine.py` | Detector/evidence/risk/action references | Pipeline fixture evidence subset assertion | PASS |
| Incident alert | SQLite incident store at ≥50 | Actual demo incident IDs in JSON artifact | Incident create/read/status pipeline test | PARTIAL |
| External alerts / SIEM | Not present | No integration code | None | NOT IMPLEMENTED |
| Automated destructive response | Not present by design | All response entries manual/approval-required | Pipeline tests assert automatic execution false | PASS |
| Multimedia manipulation ML | Adapter interfaces only; no validated model | No multimedia model/dataset installed | No automated multimedia test | NOT IMPLEMENTED |
| Multimedia metadata inspection | `detectors/multimedia.py` | PNG/WAV/MP4 synthetic uploads; ffmpeg tools absent | Manual API upload checks | PARTIAL |
| Identity/context risk | `assess_identity_context` + fusion category | Demo returns identity_impersonation from context rules | Multimedia demo | PARTIAL |
| Dashboard API authentication | None; loopback bind only | Anonymous `/api/dashboard` returned 200 | Manual API request | NOT IMPLEMENTED |
| API malformed-input behavior | `backend/web.py`, `backend/service.py` | Two malformed requests returned 500 | Manual malformed probes | PARTIAL |
| Incident transition audit trail | Status overwritten, no event record | Database schema only has current status/payload | Status route checks | PARTIAL |
| API/UX integration regression tests | None | No API test module | Full suite collection | NOT IMPLEMENTED |
| Installable packaged app | `pyproject.toml` include list omits fusion/risk/response/explainability/database/frontend and policy data | Packaging configuration inspection | No wheel build/install test | NOT IMPLEMENTED |
| Documentation matches implementation | Root README still says no dashboard and frontend reserved; evaluation docs use old module paths | Direct comparison with current files | Static audit | PARTIAL |

## K. Demo validation: exact actual outputs

The full HTTP response bodies, including every detector result, confidence, limitation, evidence item, fusion decision, risk contributor, explanation, response action, incident ID, and processing time, are saved in [`technical_audit_demos.json`](technical_audit_demos.json). They were freshly collected from the live dashboard API during this audit.

| Scenario | Detector outputs | Fused threat / agreement | Risk / incident | Evidence → explanation → response |
|---|---|---|---|---|
| Phishing | `phishing_nlp: phishing` (confidence null); rules: urgency + credential request | `phishing` / multi-detector agreement | **50 high**, incident `40b9d555-6be2-4367-826a-c238b5ca87b0` | 2 rule evidence items; template says email phishing assessment and names both detector outputs; 5 advisory actions (quarantine, warn, inspect, credential exposure review, analyst escalation). |
| Phishing + URL | NLP phishing, rule indicators, URL lexical suspicious | `phishing` / multi-detector agreement | **92 critical**, incident `3d056e37-f0e2-4a50-9a6d-2e75542f5be2` | 6 evidence items; explanation lists actual detector signals, risk contributors, limits; 6 advisory actions. URL uses `192.0.2.44`, a documentation-range address, and was not visited. |
| Account takeover | Login rules and Isolation Forest both anomalous; model confidence null | `account_takeover` / multi-detector agreement | **80 critical**, incident `94e460c3-f0fa-4f47-aad6-bcfc23e1b764` | 4 evidence items: repeated failures, success after failures, unusual hour, IF outlier; explanation reports synthetic limitations; 5 advisory actions. |

The exact captured phishing risk contributors were `credential_request +20`, `detector_agreement +15`, `urgency +10`, `asset_sensitivity +5` = 50. The account-takeover total was base 10 + agreement 15 + IF outlier 10 + repeated failures 12 + success after failures 20 + unusual hour 8 + asset sensitivity 5 = 80.

## L. Safe and unsafe judge claims

**Safe to claim:** a reproducible-protocol supervised email text baseline was trained/evaluated on a documented historical CC BY dataset; the current linear SVM is called at inference and emits no probability; deterministic email/URL/login rules contribute separate evidence; a synthetic Isolation Forest baseline is called at inference; outputs flow through categorical fusion, configurable evidence-weighted risk, structured explanations, and an advisory response policy; qualifying results create local SQLite incidents; suspicious URLs are never automatically fetched; multimedia currently produces cautious metadata/context assessments without a deepfake claim.

**Do not claim:** universal phishing detection; phishing metrics representative of present-day traffic; calibrated phishing confidence; real-world account-takeover detection performance; live malicious-URL reputation or safe URL verdicts; image/audio/video deepfake or synthetic-speech detection; identity verification; external alerting/SIEM; authenticated multi-user SOC; production-ready API security, availability, or incident auditability; automatic containment; packaged wheel installation working.

## M. Remaining blockers before broader use

1. Fix `analyze-media` CLI dispatch and stale README/evaluation paths.
2. Validate request object shapes and optional email field types; return consistent 4xx errors and avoid exposing internal exception text.
3. Add automated API and multimedia tests, plus regression cases for malformed inputs and fusion/risk disagreement.
4. Restrict risk contributors to validated, relevant supporting evidence; validate all policy weights and levels.
5. Add authentication/authorization and request/concurrency/resource limits before any non-loopback deployment; add audit events for incident status changes.
6. Verify model artifact hashes/signatures before pickle loading; pin training/runtime library versions for reproducibility.
7. Treat ffprobe/ffmpeg as untrusted-media attack surface; bound resources and protocol access before installing/enabling them.
8. Include all required Python packages, JSON policy, and frontend assets in distribution metadata and verify a clean wheel install.

**Audit conclusion:** the repository is a functioning local hackathon prototype with a real but narrow phishing text model and a synthetic login anomaly model. Its fusion/risk/incident path is demonstrable. It is not a production SOC service, and multimedia manipulation/identity verification is not an ML capability in this build.
