from pathlib import Path
import webview

from .api import Api


def main():
    # web directory lives at repository root; go up one level from this package
    html_path = Path(__file__).parent.parent / "web" / "index.html"
    url = html_path.resolve().as_uri()
    api = Api()
    webview.create_window("pywebview Demo", url, width=900, height=700, js_api=api)
    webview.start()


if __name__ == "__main__":
    main()
