from __future__ import annotations

from pathlib import Path
import sys

from PySide6 import QtCore, QtWidgets


TRANSLATION_PREFIX = "cswave"
TRANSLATION_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "translations"


def install_translator(app: QtWidgets.QApplication, locale: str | None = None) -> str | None:
    """Install a Qt translator for the requested locale.

    If locale is None, empty, "system", or "auto", the system locale is used.
    English is the source language and fallback, so missing translation files are not an error.
    The loaded translator is stored on the QApplication to keep it alive for the process lifetime.
    """
    requested_locale = system_locale_name() if _uses_system_locale(locale) else locale
    for candidate in _locale_candidates(requested_locale):
        path = TRANSLATION_DIR / f"{TRANSLATION_PREFIX}_{candidate}.qm"
        if not path.exists():
            continue
        translator = QtCore.QTranslator(app)
        if not translator.load(str(path)):
            continue
        app.installTranslator(translator)
        translators = getattr(app, "_cswave_translators", [])
        translators.append(translator)
        setattr(app, "_cswave_translators", translators)
        return candidate
    return None


def system_locale_name() -> str:
    return QtCore.QLocale.system().name()


def _uses_system_locale(locale: str | None) -> bool:
    return locale is None or locale.strip().lower() in {"", "system", "auto"}


def _locale_candidates(locale: str | None) -> list[str]:
    if not locale:
        return []
    normalized = locale.replace("-", "_")
    candidates = [normalized]
    language = normalized.split("_", 1)[0]
    if language and language not in candidates:
        candidates.append(language)
    return [candidate for candidate in candidates if candidate and candidate.lower() != "en"]
