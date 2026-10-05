# CYBERGUARD Intelligence Dashboard

Run `run.bat` from the repository root on Windows. It checks dependencies and model artifacts, initializes the synthetic login model if needed, and starts the local dashboard. Or start the local, loopback-only dashboard manually from the repository root:

```powershell
& .\.venv\Scripts\python.exe -m backend.web
```

Open `http://127.0.0.1:8765`. The dashboard uses the actual detector adapters and `backend.pipeline.analyze`; no browser-side model or fabricated detection animation is used. Analysis history metrics are stored in ignored `database/dashboard.sqlite3`; threshold incidents use the shared `database/incidents.sqlite3` store.

The dashboard opens on **New analysis** with the existing detector selector. Choose **Email** and paste the full email once; MIME text parts, sender, organization and role clues, likely objective, attachment names, visible URLs, and HTML link destinations are extracted when present. This uses the existing Email analysis route, while SMS, Social, QR code, URL, Website, Login, Image, Audio, and Video modes remain available. Pasted-email fields are extracted as message context only; there is no impersonation detector. Text-derived claims and authentication results included in pasted headers are not independently verified.

The detector does not guarantee detection of every malicious email. The bundled model's reported test metrics come from a random split of a historical merged-source corpus and do not establish present-day performance. URL reputation is not queried online; only provided content and offline lexical/domain features are assessed.

Demo scenarios are integrated into the top-right **Demo scenarios** control on **New analysis**. Selecting a scenario only prefills the matching email, message, URL, website, login, image, audio, or video form; the detector pipeline runs only after the user selects **Analyze**. Synthetic runs use `/api/analyze-demo`, are labelled, and are excluded from both the incident queue and dashboard analysis totals. Real requests use `/api/analyze`; a client-supplied demo marker cannot suppress persistence for real analyses. Media fixture bytes are supplied by the local `/api/demo-fixture/<fixture>` endpoint. Multimedia metadata remains inconclusive and is not presented as proof of a deepfake. All scores and evidence displayed after analysis are backend results. Media uploads are capped at 100 MiB and temporary analysis copies are deleted. The service binds to loopback by default and refuses non-loopback bind addresses.

The dashboard overview includes a **Register complaint** shortcut to the official Indian Cyber Crime Reporting Portal. Threat-qualified live analysis results also offer an editable complaint draft, but CyberGuard never submits messages, identity documents, or complaint details automatically.

Incident status actions update local case state (`open`, `acknowledged`, `investigating`, `resolved`). They do not execute containment, account, or other response actions. A future multimedia UI must continue to display `features.user_facing_limitation` and detector `limitations` verbatim.

Only live `/api/analyze` requests that meet the configured risk threshold create persisted incidents. Synthetic demo runs are not added to the incident store. Incident records include a `live_analysis` source and a limited input summary; raw email/message bodies are not retained in that summary. Legacy incidents without source provenance are hidden from the dashboard incident list.
