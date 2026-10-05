"""CLI for detector output inspection and offline evaluation."""
import argparse
import json
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(prog="cyberguard")
    subs = parser.add_subparsers(dest="command", required=True)
    train = subs.add_parser("train", help="compare phishing NLP baselines on supplied authorized CSV")
    train.add_argument("--csv", required=True)
    train.add_argument("--output", required=True)
    sync = subs.add_parser("sync-registry", help="attach dataset provenance to an existing model")
    sync.add_argument("--model", required=True)
    sync.add_argument("--csv", required=True)
    prepare = subs.add_parser("prepare-dataset", help="normalize an authorized source CSV with explicit columns/labels")
    prepare.add_argument("--input", required=True)
    prepare.add_argument("--output", required=True)
    prepare.add_argument("--text-column", required=True)
    prepare.add_argument("--label-column", required=True)
    prepare.add_argument("--phishing-label", required=True)
    prepare.add_argument("--benign-label", required=True)
    email = subs.add_parser("analyze-email", help="run a trained phishing text baseline")
    email.add_argument("--model", required=True)
    email.add_argument("--text", required=True)
    email_rules = subs.add_parser("analyze-email-rules", help="run independent phishing indicator rules")
    email_rules.add_argument("--text", required=True)
    email_rules.add_argument("--sender")
    email_rules.add_argument("--url")
    url = subs.add_parser("analyze-url", help="inspect URL lexical features without fetching it")
    url.add_argument("--url", required=True)
    login = subs.add_parser("analyze-login", help="run login rules on one event JSON object")
    login_source = login.add_mutually_exclusive_group(required=True)
    login_source.add_argument("--json")
    login_source.add_argument("--json-file")
    evaluate_login = subs.add_parser("evaluate-login-ml", help="evaluate and serialize Isolation Forest on synthetic ground truth")
    evaluate_login.add_argument("--output", default="models/login")
    ml_login = subs.add_parser("analyze-login-ml", help="run the synthetic Isolation Forest inference model")
    ml_login.add_argument("--model", default="models/login/model.joblib")
    ml_login_source = ml_login.add_mutually_exclusive_group(required=True)
    ml_login_source.add_argument("--json")
    ml_login_source.add_argument("--json-file")
    media = subs.add_parser("analyze-media", help="run cautious image, audio, or video metadata assessment")
    media.add_argument("--type", choices=("image", "audio", "video"), required=True)
    media.add_argument("--file", required=True)
    demo = subs.add_parser("demo", help="run all current detectors on synthetic local examples")
    demo.add_argument("--phishing-model", default="models/phishing/model.joblib")
    demo.add_argument("--login-model", default="models/login/model.joblib")
    demo.add_argument("--login-input", default="datasets/demo_login.json")
    demo.add_argument("--output-file")
    args = parser.parse_args(argv)
    try:
        if args.command == "analyze-media":
            from detectors.multimedia import analyze_audio, analyze_image, analyze_video
            analyzer = {"image": analyze_image, "audio": analyze_audio, "video": analyze_video}[args.type]
            result = analyzer(args.file).to_dict()
        elif args.command == "demo":
            from backend.demo import run_demo
            result = run_demo(args.phishing_model, args.login_model, args.login_input)
            rendered = json.dumps(result, indent=2)
            if args.output_file:
                from pathlib import Path
                Path(args.output_file).write_text(rendered, encoding="utf-8")
            print(rendered)
            return 0
        if args.command == "prepare-dataset":
            from training.prepare_dataset import prepare_csv
            result = prepare_csv(args.input, args.output, args.text_column, args.label_column,
                                 args.phishing_label, args.benign_label)
        elif args.command == "sync-registry":
            from training.phishing import refresh_existing_registry
            result = refresh_existing_registry(args.model, args.csv)
        elif args.command == "train":
            from training.phishing import train_and_evaluate
            result = train_and_evaluate(args.csv, args.output)
        elif args.command == "analyze-email":
            from detectors.phishing import PhishingNLPDetector
            result = PhishingNLPDetector(args.model).analyze(args.text).to_dict()
        elif args.command == "analyze-email-rules":
            from detectors.phishing_rules import PhishingSecurityRulesDetector
            result = PhishingSecurityRulesDetector().analyze(args.text, args.sender, args.url).to_dict()
        elif args.command == "analyze-url":
            from detectors.url import analyze_url
            result = analyze_url(args.url).to_dict()
        elif args.command == "analyze-login":
            from detectors.login import analyze_login
            event_json = args.json if args.json is not None else open(args.json_file, encoding="utf-8").read()
            result = analyze_login(json.loads(event_json)).to_dict()
        elif args.command == "analyze-login-ml":
            from detectors.login_ml import LoginIsolationForestDetector
            event_json = args.json if args.json is not None else open(args.json_file, encoding="utf-8").read()
            result = LoginIsolationForestDetector(args.model).analyze(json.loads(event_json)).to_dict()
        else:
            from training.login import evaluate_isolation_forest
            result = evaluate_isolation_forest(output_dir=args.output)
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
