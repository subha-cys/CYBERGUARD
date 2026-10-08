"""Assemble the unpacked Chrome extension from the shared dashboard assets."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve().parent
OUTPUT = SOURCE / "build"
API_BASE = "http://127.0.0.1:8765"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    for name in ("manifest.json", "background.js", "content.js", "popup.html", "popup.css", "popup.js"):
        shutil.copy2(SOURCE / name, OUTPUT / name)

    dashboard = OUTPUT / "dashboard"
    dashboard.mkdir(exist_ok=True)
    for name in ("app.js", "styles.css"):
        shutil.copy2(ROOT / "frontend" / name, dashboard / name)

    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    html = html.replace('href="/styles.css', 'href="./styles.css')
    html = html.replace('src="/app.js', 'src="./app.js')
    html = html.replace(
        '<script src="./app.js?v=16" defer></script>',
        f'<script>window.CYBERGUARD_API_BASE={json.dumps(API_BASE)};</script>\n'
        '<script src="./app.js?v=16" defer></script>',
    )
    (dashboard / "index.html").write_text(html, encoding="utf-8")
    print(f"Built unpacked extension at: {OUTPUT}")


if __name__ == "__main__":
    main()