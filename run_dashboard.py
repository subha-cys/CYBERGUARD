"""VS Code editor-run entry point for the local CYBERGUARD dashboard."""
from backend.web import main


if __name__ == "__main__":
    main(["--host", "127.0.0.1", "--port", "8765", "--open-browser"])
