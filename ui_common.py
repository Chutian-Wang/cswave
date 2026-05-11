from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


def ui_tr(text: str) -> str:
    return QtCore.QCoreApplication.translate("viewer", text)


class DetachedTabWindow(QtWidgets.QDialog):
    def __init__(
        self,
        tab_widget: DetachableTabWidget,
        widget: QtWidgets.QWidget,
        title: str,
        index: int,
    ) -> None:
        super().__init__(tab_widget.window())
        self._tab_widget = tab_widget
        self._widget = widget
        self._title = title
        self._index = index
        self._reattached = False
        self.setWindowTitle(title)
        self.resize(360, 620)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        widget.setParent(self)
        layout.addWidget(widget)
        widget.show()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.reattach()
        event.accept()

    def reattach(self) -> None:
        if self._reattached:
            return
        self._reattached = True
        self.layout().removeWidget(self._widget)
        self._widget.hide()
        self._tab_widget.reattach_tab(self._widget, self._title, self._index)


class DetachableTabWidget(QtWidgets.QTabWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._detached_windows: dict[QtWidgets.QWidget, DetachedTabWindow] = {}
        self.tabBarDoubleClicked.connect(self.detach_tab)

    def detach_tab(self, index: int) -> None:
        if index < 0:
            return
        widget = self.widget(index)
        if widget is None or widget in self._detached_windows:
            return
        title = self.tabText(index)
        self.removeTab(index)
        window = DetachedTabWindow(self, widget, title, index)
        self._detached_windows[widget] = window
        window.show()

    def reattach_tab(self, widget: QtWidgets.QWidget, title: str, index: int) -> None:
        self._detached_windows.pop(widget, None)
        insert_at = min(index, self.count())
        self.insertTab(insert_at, widget, title)
        self.setCurrentWidget(widget)
        widget.show()


class VerticalTextButton(QtWidgets.QPushButton):
    def __init__(self, text: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QtCore.QSize:
        base = super().sizeHint()
        return QtCore.QSize(max(24, base.height() + 8), max(84, base.width() + 24))

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        _ = event
        option = QtWidgets.QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ""
        painter = QtGui.QPainter(self)
        self.style().drawControl(QtWidgets.QStyle.ControlElement.CE_PushButton, option, painter, self)
        painter.setPen(self.palette().buttonText().color())
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(-90)
        text_rect = QtCore.QRectF(-self.height() / 2, -self.width() / 2, self.height(), self.width())
        painter.drawText(text_rect, QtCore.Qt.AlignmentFlag.AlignCenter, self.text())


def operand_picker_row(combo: QtWidgets.QComboBox, button: QtWidgets.QPushButton) -> QtWidgets.QWidget:
    row = QtWidgets.QWidget()
    row.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
    layout = QtWidgets.QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter)
    expand_horizontally(combo)
    keep_button_to_hint(button)
    layout.addWidget(combo, stretch=1, alignment=QtCore.Qt.AlignmentFlag.AlignVCenter)
    layout.addWidget(button, alignment=QtCore.Qt.AlignmentFlag.AlignVCenter)
    return row


def configure_panel_form(form: QtWidgets.QFormLayout) -> None:
    form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.DontWrapRows)
    form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
    form.setHorizontalSpacing(10)
    form.setVerticalSpacing(8)


def expand_horizontally(widget: QtWidgets.QWidget) -> None:
    policy = widget.sizePolicy()
    policy.setHorizontalPolicy(QtWidgets.QSizePolicy.Policy.Expanding)
    widget.setSizePolicy(policy)
    if isinstance(widget, QtWidgets.QComboBox):
        widget.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        widget.setMinimumContentsLength(10)


def keep_button_to_hint(button: QtWidgets.QAbstractButton) -> None:
    policy = button.sizePolicy()
    policy.setHorizontalPolicy(QtWidgets.QSizePolicy.Policy.Fixed)
    button.setSizePolicy(policy)
    button.setMinimumWidth(max(button.minimumSizeHint().width(), button.sizeHint().width()))


def horizontal_separator() -> QtWidgets.QFrame:
    line = QtWidgets.QFrame()
    line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
    line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
    return line


def blend_colors(base: QtGui.QColor, overlay: QtGui.QColor, amount: float) -> QtGui.QColor:
    amount = max(0.0, min(1.0, amount))
    return QtGui.QColor(
        round(base.red() * (1.0 - amount) + overlay.red() * amount),
        round(base.green() * (1.0 - amount) + overlay.green() * amount),
        round(base.blue() * (1.0 - amount) + overlay.blue() * amount),
    )


def contrasting_text_color(background: QtGui.QColor) -> QtGui.QColor:
    return QtGui.QColor("#ffffff") if background.lightness() < 140 else QtGui.QColor("#000000")


def scale_selector(parent: QtWidgets.QWidget | None = None) -> QtWidgets.QComboBox:
    combo = QtWidgets.QComboBox(parent)
    combo.addItem(ui_tr("Auto"), "auto")
    for prefix, exponent in SI_PREFIXES:
        label = ui_tr("(no scale)") if prefix == "" else prefix
        combo.addItem(label, exponent)
    expand_horizontally(combo)
    return combo


SI_PREFIXES: tuple[tuple[str, int], ...] = (
    ("p", -12),
    ("n", -9),
    ("µ", -6),
    ("m", -3),
    ("", 0),
    ("k", 3),
    ("M", 6),
    ("G", 9),
    ("T", 12),
)
SI_PREFIX_BY_EXPONENT = {exponent: prefix for prefix, exponent in SI_PREFIXES}


def format_value(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.8g}"


def format_scaled_value(value: float | None, unit: str | None, scale: object = "auto") -> str:
    if value is None or not np_isfinite(value):
        return "-"
    exponent = scale_exponent(value, scale)
    scaled = float(value) / (10.0 ** exponent)
    suffix = f"{SI_PREFIX_BY_EXPONENT.get(exponent, '')}{unit or ''}"
    text = format_value(scaled)
    return f"{text} {suffix}".rstrip()


def scale_exponent(value: float, scale: object) -> int:
    if isinstance(scale, int):
        return scale
    if isinstance(scale, str) and scale != "auto":
        try:
            return int(scale)
        except ValueError:
            return 0
    magnitude = abs(float(value))
    if magnitude == 0 or not np_isfinite(magnitude):
        return 0
    chosen = 0
    for _prefix, exponent in SI_PREFIXES:
        scaled = magnitude / (10.0 ** exponent)
        if 1.0 <= scaled < 1000.0:
            return exponent
        if magnitude >= 10.0 ** exponent:
            chosen = exponent
    return chosen


def np_isfinite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))
