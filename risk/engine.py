"""Transparent, reproducible security risk scoring. Confidence is not risk."""
import json
from pathlib import Path

DEFAULT_POLICY = Path(__file__).with_name("risk_policy.json")


class RiskEngine:
    def __init__(self, policy_path: str | Path = DEFAULT_POLICY):
        self.policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
        self._validate_policy()

    def _validate_policy(self):
        levels = self.policy["levels"]
        if not levels or levels[0]["min"] != 0 or levels[-1]["max"] != 100:
            raise ValueError("risk levels must cover 0 through 100")
        for left, right in zip(levels, levels[1:]):
            if left["max"] + 1 != right["min"]:
                raise ValueError("risk level ranges must be contiguous and non-overlapping")
        if not 0 <= self.policy["incident_min_score"] <= 100:
            raise ValueError("incident_min_score must be in [0, 100]")

    def assess(self, fusion: dict, asset_sensitivity: str = "medium") -> dict:
        if asset_sensitivity not in self.policy["asset_sensitivity_points"]:
            raise ValueError("asset_sensitivity must be low, medium, high, or critical")
        weights = self.policy["evidence_points"]
        total = self.policy["threat_base_points"].get(fusion["threat"], 0)
        contributors = []
        if total:
            contributors.append({"factor": "threat_base", "points": total, "reason": fusion["threat"]})

        observed = set()
        if any(x["detector"] == "url_lexical" and x["normalized_signal"] == "support" for x in fusion["detector_results"]):
            observed.add("suspicious_url")
        aliases = {"sender_domain_mismatch": "domain_anomaly"}
        for evidence in fusion["evidence"]:
            indicator = aliases.get(evidence.get("indicator"), evidence.get("indicator"))
            if indicator in weights and indicator != "suspicious_url":
                observed.add(indicator)
        if len(fusion["supporting_detectors"]) >= 2:
            observed.add("detector_agreement")
        for factor in sorted(observed):
            points = weights[factor]
            contributors.append({"factor": factor, "points": points, "reason": "observed in structured detector output"})
            total += points

        asset_points = self.policy["asset_sensitivity_points"][asset_sensitivity] if fusion["threat"] not in {"benign", "no_threat_detected", "undetermined"} else 0
        if asset_points:
            contributors.append({"factor": "asset_sensitivity", "points": asset_points, "reason": asset_sensitivity})
            total += asset_points
        score = min(100, total)
        corroboration_cap_applied = False
        level = next(x["name"] for x in self.policy["levels"] if x["min"] <= score <= x["max"])
        return {
            "policy_version": self.policy["version"], "risk_score": score, "severity": level,
            "contributors": contributors, "uncapped_total": total,
            "corroboration_cap_applied": corroboration_cap_applied,
            "incident_threshold": self.policy["incident_min_score"],
            "incident_required": score >= self.policy["incident_min_score"],
            "asset_sensitivity": asset_sensitivity,
            "model_confidence_is_not_risk": True,
        }
