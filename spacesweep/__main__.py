"""Entry point: `python -m spacesweep` (native window) or `--browser`."""

import argparse
import os
import sys

from . import APP_NAME, __version__
from .api import Api


def ui_dir():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "ui")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="spacesweep", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--browser", action="store_true", help="open the UI in your web browser instead of a window")
    parser.add_argument("--port", type=int, default=0, help="port for --browser mode (default: random)")
    parser.add_argument("--no-open", action="store_true", help="with --browser: don't open a browser tab")
    parser.add_argument("--debug", action="store_true", help="enable the WebView developer tools")
    args = parser.parse_args(argv)

    api = Api()
    if not args.browser:
        try:
            import webview
        except ImportError:
            print("pywebview no está instalado; abriendo en el navegador. / pywebview missing; using the browser.")
        else:
            window = webview.create_window(
                APP_NAME, os.path.join(ui_dir(), "index.html"), js_api=api,
                width=1240, height=820, min_size=(940, 620), background_color="#0f1115",
            )
            api._window = window
            try:
                webview.start(debug=args.debug)
                return
            except Exception as exc:  # e.g. WebView2 runtime missing
                api._window = None
                print(f"No se pudo abrir la ventana ({exc}); usando el navegador.")

    from .server import serve
    serve(api, ui_dir(), port=args.port, open_browser=not args.no_open)


if __name__ == "__main__":
    main()
