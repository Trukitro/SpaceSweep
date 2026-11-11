"""Entry point: `python -m spacesweep` (native window) or `--browser`."""

import argparse
import os
import sys

from . import APP_NAME, __version__
from .api import Api


def ui_dir():
    if hasattr(sys, "_MEIPASS"):  # PyInstaller build
        return os.path.join(sys._MEIPASS, "spacesweep", "ui")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="spacesweep", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--browser", action="store_true", help="open the UI in your web browser instead of a window")
    parser.add_argument("--port", type=int, default=0, help="port for --browser mode (default: random)")
    parser.add_argument("--no-open", action="store_true", help="with --browser: don't open a browser tab")
    parser.add_argument("--debug", action="store_true", help="enable the WebView developer tools")
    parser.add_argument("--check", action="store_true", help="background check: free-space alert + Downloads rules, then exit")
    parser.add_argument("--clean-safe", action="store_true", help="clean the 'safe' Cleanup group on the system drive, then exit")
    parser.add_argument("--open", metavar="PATH", help="open the Disk explorer on PATH (used by the Explorer right-click entry)")
    args = parser.parse_args(argv)

    if args.check or args.clean_safe:  # scheduled-task modes: no window, exit when done
        from . import automation
        result = automation.run_check() if args.check else automation.run_clean_safe()
        if sys.stdout:
            print(result)
        return

    api = Api()
    if args.open and os.path.isdir(args.open):
        api._startup_path = os.path.abspath(args.open)
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
