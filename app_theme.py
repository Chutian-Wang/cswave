from __future__ import annotations

from PySide6 import QtGui, QtWidgets


def apply_dark_theme(app: QtWidgets.QApplication) -> None:
    """Apply a consistent dark Qt widget theme across platforms."""
    _remember_system_theme(app)
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    app.setStyleSheet(
        """
        QToolTip {
            color: #f0f2f4;
            background-color: #2d3035;
            border: 1px solid #5a5f68;
            padding: 3px;
        }
        QGroupBox {
            border: 1px solid #4a4f58;
            border-radius: 4px;
            margin-top: 0.7em;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 3px;
        }
        QLineEdit, QComboBox, QListWidget, QTableWidget, QTextEdit, QPlainTextEdit {
            selection-background-color: #17181c;
            selection-color: #ffffff;
        }
        """
    )


def apply_system_theme(app: QtWidgets.QApplication) -> None:
    """Restore the platform/default Qt theme captured before dark mode."""
    style_name = app.property("_cswave_system_style") or ""
    palette = app.property("_cswave_system_palette")
    stylesheet = app.property("_cswave_system_stylesheet")
    if style_name:
        app.setStyle(str(style_name))
    if isinstance(palette, QtGui.QPalette):
        app.setPalette(palette)
    else:
        app.setPalette(QtWidgets.QApplication.style().standardPalette())
    app.setStyleSheet(str(stylesheet or ""))


def _remember_system_theme(app: QtWidgets.QApplication) -> None:
    if app.property("_cswave_system_theme_saved"):
        return
    app.setProperty("_cswave_system_theme_saved", True)
    app.setProperty("_cswave_system_style", app.style().objectName())
    app.setProperty("_cswave_system_palette", QtGui.QPalette(app.palette()))
    app.setProperty("_cswave_system_stylesheet", app.styleSheet())


def dark_palette() -> QtGui.QPalette:
    palette = QtGui.QPalette()
    active = QtGui.QPalette.ColorGroup.Active
    inactive = QtGui.QPalette.ColorGroup.Inactive
    disabled = QtGui.QPalette.ColorGroup.Disabled

    colors = {
        QtGui.QPalette.ColorRole.Window: "#17181c",
        QtGui.QPalette.ColorRole.WindowText: "#f0f2f4",
        QtGui.QPalette.ColorRole.Base: "#17181c",
        QtGui.QPalette.ColorRole.AlternateBase: "#131416",
        QtGui.QPalette.ColorRole.ToolTipBase: "#1c1e21",
        QtGui.QPalette.ColorRole.ToolTipText: "#f0f2f4",
        QtGui.QPalette.ColorRole.Text: "#f0f2f4",
        QtGui.QPalette.ColorRole.Button: "#212328",
        QtGui.QPalette.ColorRole.ButtonText: "#f0f2f4",
        QtGui.QPalette.ColorRole.BrightText: "#ffffff",
        QtGui.QPalette.ColorRole.Link: "#7db1ff",
        QtGui.QPalette.ColorRole.Highlight: "#3d7eff",
        QtGui.QPalette.ColorRole.HighlightedText: "#ffffff",
    }
    for role, color in colors.items():
        palette.setColor(active, role, QtGui.QColor(color))
        palette.setColor(inactive, role, QtGui.QColor(color))

    disabled_text = QtGui.QColor("#858b94")
    disabled_base = QtGui.QColor("#202227")
    disabled_button = QtGui.QColor("#101214")
    palette.setColor(disabled, QtGui.QPalette.ColorRole.Window, QtGui.QColor("#131417"))
    palette.setColor(disabled, QtGui.QPalette.ColorRole.WindowText, disabled_text)
    palette.setColor(disabled, QtGui.QPalette.ColorRole.Text, disabled_text)
    palette.setColor(disabled, QtGui.QPalette.ColorRole.ButtonText, disabled_text)
    palette.setColor(disabled, QtGui.QPalette.ColorRole.Base, disabled_base)
    palette.setColor(disabled, QtGui.QPalette.ColorRole.Button, disabled_button)
    palette.setColor(disabled, QtGui.QPalette.ColorRole.Highlight, QtGui.QColor("#1d2026"))
    palette.setColor(disabled, QtGui.QPalette.ColorRole.HighlightedText, disabled_text)
    return palette
