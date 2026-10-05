# Detection foundation evaluation

Generated during the CYBERGUARD Phase 1 implementation. Metrics below are measured by `backend.training.phishing` and `backend.training.login`; they are not estimates.

## Phishing text baseline

- **Dataset:** Alhuzali et al., [Phishing-Email-Detection-Dataset](https://doi.org/10.5281/zenodo.17314806), Zenodo v2, CC BY 4.0.
- **Source artifact:** `Balanced_Dataset.csv`; publisher MD5 `c18127659164566291c18803cc7d4c5f` verified during import.
- **Label semantics:** source `1.0` combines phishing, spam, and scam; `0.0` is safe/benign. This is not a pure phishing-versus-ham label.
- **Preprocessing:** `body` mapped to text, exact duplicate `(text,label)` rows removed; no hand-authored training samples.
- **Counts after import:** 98,085 positive and 95,619 benign; 4,746 duplicate/empty records removed; imbalance ratio 1.026.
- **Split:** stratified random train/validation/test with 135,592 / 29,056 / 29,056 rows and fixed seeds documented in the model registry.
- **Features:** word TF-IDF, unigrams and bigrams, `min_df=2`, maximum 50,000 features.
- **Selection:** Logistic Regression and Linear SVM compared on validation macro-F1. Linear SVM selected.

| Model | Validation accuracy | Macro precision | Macro recall | Macro F1 |
|---|---:|---:|---:|---:|
| Logistic Regression | 0.9804 | 0.9804 | 0.9804 | 0.9804 |
| Linear SVM | 0.9848 | 0.9849 | 0.9848 | 0.9848 |

Held-out test metrics for the selected Linear SVM:

| Accuracy | Macro precision | Macro recall | Macro F1 |
|---:|---:|---:|---:|
| 0.9852 | 0.9853 | 0.9851 | 0.9852 |

Confusion matrix with rows = actual `[benign, phishing]` and columns = predicted `[benign, phishing]`:

```text
[[14071,   272],
 [  158, 14555]]
```

The Linear SVM does not produce a calibrated probability; inference sets confidence to `null`. The score above is not a real-world performance claim. The source corpus combines nine historical public corpora, covers 1998–2008, groups spam and scams with phishing, and a random split may share corpus/campaign artifacts. No temporal or independent external test was run.

## Login anomaly baseline

- **Dataset:** reproducible synthetic events generated in `backend/datasets/login_synthetic.py`, seed 17, 1,000 rows.
- **Ground truth:** 20% generated with UTC login hour 00–04 and 5–9 failed attempts; normal records use hour 07–20 and 0–2 failures. No real account history is represented.
- **Model:** StandardScaler + Isolation Forest, 200 trees, `contamination=0.20`; trained using only normal records in the training partition.
- **Held-out synthetic test set:** 300 events.

| Precision | Recall | F1 |
|---:|---:|---:|
| 0.5455 | 1.0000 | 0.7059 |

Confusion matrix, rows = actual `[normal, anomaly]`, columns = predicted `[normal, anomaly]`:

```text
[[190, 50],
 [  0, 60]]
```

The false-positive count is 50 out of 240 normal events. The metrics measure recovery of intentionally separable generated patterns only and do not show real-world account takeover performance. The inference adapter returns the model's decision function score as a feature, not confidence.

## Reproduction

```powershell
& .\.venv\Scripts\python.exe -m backend.cli train --csv datasets\phishing_email.csv --output models\phishing
& .\.venv\Scripts\python.exe -m backend.cli evaluate-login-ml --output models\login
& .\.venv\Scripts\python.exe -m pytest -vv
```
