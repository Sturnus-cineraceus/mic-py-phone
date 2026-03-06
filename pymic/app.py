from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler
import webview

from .api import Api


def _configure_logging():
    try:
        root = logging.getLogger()
        # avoid double-configuring if already set up
        if root.handlers:
            return
        # ensure logs dir exists at repo root
        logs_dir = Path(__file__).parent.parent / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = logs_dir / "pymic.log"

        fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

        fh = RotatingFileHandler(
            str(log_file), maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        fh.setFormatter(fmt)
        fh.setLevel(logging.DEBUG)

        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        ch.setLevel(logging.INFO)

        root.setLevel(logging.DEBUG)
        root.addHandler(fh)
        root.addHandler(ch)
    except Exception:
        # best-effort only; do not crash the app if logging setup fails
        pass


def main():
    # configure logging early so modules can log failures to file
    _configure_logging()

    # web directory lives at repository root; go up one level from this package
    html_path = Path(__file__).parent.parent / "web" / "index.html"
    url = html_path.resolve().as_uri()
    api = Api()
    webview.create_window(
        "pymic - Audio Bypass", url, width=900, height=700, js_api=api
    )
    webview.start()


if __name__ == "__main__":
    main()
