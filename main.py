from __future__ import annotations

import argparse
import sys

from app_info import APP_ID, APP_NAME, APP_VERSION
from viewer import MainWindow
from PySide6 import QtWidgets
from localization import install_translator


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CSV waveform viewer")
    parser.add_argument("csv", nargs="?", help="Optional CSV or Excel waveform file to open at startup")
    parser.add_argument("--language", help="Startup locale, for example zh_CN. Defaults to the system language.")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_ID)
    install_translator(app, args.language)
    window = MainWindow(startup_language=args.language or "system")
    if args.csv:
        window.load_file(args.csv, show_setup=True)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
