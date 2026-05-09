from __future__ import annotations

import argparse
import sys

from viewer import MainWindow
from PySide6 import QtWidgets


def main() -> int:
    parser = argparse.ArgumentParser(description="CSV waveform viewer")
    parser.add_argument("csv", nargs="?", help="Optional CSV file to open at startup")
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    if args.csv:
        window.load_file(args.csv, show_setup=True)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
