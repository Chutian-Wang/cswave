"""Preload data dependencies before PySide6 runtime initialization.

The source app intentionally imports pandas before PySide6 because the current
PySide6/shiboken feature importer can interact badly with dateutil/six during
pandas startup in frozen Python 3.12 builds. PyInstaller's PySide6 runtime hook
normally runs before application code, so this hook preserves the same safe
ordering for packaged releases.
"""

import pandas  # noqa: F401
