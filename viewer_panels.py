from __future__ import annotations

from math_engine import MATH_FUNCTIONS, WINDOW_FUNCTIONS, ZERO_PAD_OPTIONS
from PySide6 import QtCore, QtGui, QtWidgets
from ui_common import (
    blend_colors,
    configure_panel_form,
    contrasting_text_color,
    expand_horizontally,
    format_scaled_value,
    horizontal_separator,
    keep_button_to_hint,
    operand_picker_row,
    scale_selector,
)


CHANNEL_MIME_TYPE = "application/x-cswave-channel"


class DraggableChannelCheckBox(QtWidgets.QCheckBox):
    def __init__(self, name: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(name, parent)
        self.channel_name = name
        self.selection_enabled = True
        self._drag_start: QtCore.QPoint | None = None

    def set_selection_enabled(self, enabled: bool) -> None:
        self.selection_enabled = enabled
        self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor if not enabled else QtCore.Qt.CursorShape.ArrowCursor)

    def nextCheckState(self) -> None:
        if self.selection_enabled:
            super().nextCheckState()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drag_start is None or not event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            super().mouseMoveEvent(event)
            return
        distance = (event.position().toPoint() - self._drag_start).manhattanLength()
        if distance < QtWidgets.QApplication.startDragDistance():
            super().mouseMoveEvent(event)
            return
        drag = QtGui.QDrag(self)
        mime = QtCore.QMimeData()
        mime.setData(CHANNEL_MIME_TYPE, self.channel_name.encode("utf-8"))
        drag.setMimeData(mime)
        drag.exec(QtCore.Qt.DropAction.MoveAction)
        self._drag_start = None


class ChannelGroupBox(QtWidgets.QGroupBox):
    channelDropped = QtCore.Signal(str, str)

    def __init__(self, title: str, group_id: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(title, parent)
        self.group_id = group_id
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if event.mimeData().hasFormat(CHANNEL_MIME_TYPE):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:
        if event.mimeData().hasFormat(CHANNEL_MIME_TYPE):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        if not event.mimeData().hasFormat(CHANNEL_MIME_TYPE):
            event.ignore()
            return
        name = bytes(event.mimeData().data(CHANNEL_MIME_TYPE)).decode("utf-8")
        self.channelDropped.emit(name, self.group_id)
        event.acceptProposedAction()


class ChannelsPanel(QtWidgets.QWidget):
    channelMoved = QtCore.Signal(str, str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.channel_layout = QtWidgets.QVBoxLayout(self)
        self.channel_layout.setContentsMargins(8, 8, 8, 8)
        self.channel_layout.setSpacing(8)
        self.group_layouts: dict[str, QtWidgets.QVBoxLayout] = {}
        self.empty_labels: dict[str, QtWidgets.QLabel] = {}
        for group_id, title in (
            ("left", self.tr("Left Axis")),
            ("right", self.tr("Right Axis")),
            ("disabled", self.tr("Disabled")),
        ):
            box = ChannelGroupBox(title, group_id)
            box.setToolTip(self.tr("Drag channels here to assign them to this group"))
            box.channelDropped.connect(self.channelMoved)
            layout = QtWidgets.QVBoxLayout(box)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(5)
            empty = QtWidgets.QLabel(self.tr("No channels"))
            empty.setEnabled(False)
            layout.addWidget(empty)
            self.channel_layout.addWidget(box)
            self.group_layouts[group_id] = layout
            self.empty_labels[group_id] = empty
        self.channel_layout.addStretch()

    def clear_channels(self) -> None:
        for layout in self.group_layouts.values():
            while layout.count() > 1:
                item = layout.takeAt(1)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
        self._sync_empty_labels()

    def add_channel(self, group: str, checkbox: QtWidgets.QCheckBox) -> None:
        layout = self.group_layouts.get(group, self.group_layouts["disabled"])
        layout.addWidget(checkbox)
        self._sync_empty_labels()

    def _sync_empty_labels(self) -> None:
        for _group, layout in self.group_layouts.items():
            self.empty_labels[_group].setVisible(layout.count() == 1)


class CursorPanel(QtWidgets.QWidget):
    def __init__(
        self,
        *,
        x_cursor_toggle: QtWidgets.QCheckBox,
        y_cursor_toggle: QtWidgets.QCheckBox,
        cursor_axis_selector: QtWidgets.QComboBox,
        cursor_scale: QtWidgets.QComboBox,
        active_channel: QtWidgets.QComboBox,
        pick_active_channel: QtWidgets.QPushButton,
        reset_callback: object,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.cursor_labels = {
            key: QtWidgets.QLabel("-")
            for key in ("X1", "X2", "dX", "Y1", "Y2", "dY", "Active Y1", "Active Y2", "Active dY")
        }
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        controls = QtWidgets.QGroupBox(self.tr("Controls"))
        controls_layout = QtWidgets.QGridLayout(controls)
        controls_layout.setContentsMargins(8, 8, 8, 8)
        controls_layout.addWidget(x_cursor_toggle, 0, 0)
        controls_layout.addWidget(y_cursor_toggle, 0, 1)
        reset_cursors = QtWidgets.QPushButton(self.tr("Reset Cursors"))
        expand_horizontally(reset_cursors)
        reset_cursors.clicked.connect(reset_callback)
        controls_layout.addWidget(reset_cursors, 1, 0, 1, 2)
        expand_horizontally(cursor_axis_selector)
        controls_layout.addWidget(QtWidgets.QLabel(self.tr("Cursor group")), 2, 0)
        controls_layout.addWidget(cursor_axis_selector, 2, 1)
        expand_horizontally(cursor_scale)
        controls_layout.addWidget(QtWidgets.QLabel(self.tr("Scale")), 3, 0)
        controls_layout.addWidget(cursor_scale, 3, 1)
        expand_horizontally(active_channel)
        keep_button_to_hint(pick_active_channel)
        controls_layout.addWidget(QtWidgets.QLabel(self.tr("Active channel")), 4, 0)
        controls_layout.addWidget(operand_picker_row(active_channel, pick_active_channel), 4, 1)
        controls_layout.setColumnStretch(1, 1)
        layout.addWidget(controls)

        layout.addWidget(self._value_group(self.tr("X Positions"), [(self.tr("X1"), "X1"), (self.tr("X2"), "X2"), (self.tr("ΔX"), "dX")]))
        layout.addWidget(self._value_group(self.tr("Y Positions"), [(self.tr("Y1"), "Y1"), (self.tr("Y2"), "Y2"), (self.tr("ΔY"), "dY")]))
        layout.addWidget(
            self._value_group(
                self.tr("Active Channel"),
                [(self.tr("Y at X1"), "Active Y1"), (self.tr("Y at X2"), "Active Y2"), (self.tr("Delta"), "Active dY")],
            )
        )
        layout.addStretch()

    def _value_group(self, title: str, rows: list[tuple[str, str]]) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox(title)
        grid = QtWidgets.QGridLayout(box)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setHorizontalSpacing(12)
        for row, (display_name, key) in enumerate(rows):
            name_label = QtWidgets.QLabel(display_name)
            value_label = self.cursor_labels[key]
            value_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            value_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            value_label.setMinimumWidth(92)
            value_label.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont))
            grid.addWidget(name_label, row, 0)
            grid.addWidget(value_label, row, 1)
        grid.setColumnStretch(1, 1)
        return box


class MathPanel(QtWidgets.QWidget):
    def __init__(
        self,
        *,
        operand_changed: object,
        function_changed: object,
        start_operand_pick: object,
        add_output: object,
        update_fft: object,
        apply_frequency_range: object,
        output_selected: object,
        remove_output: object,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        builder = QtWidgets.QGroupBox(self.tr("Builder"))
        form = QtWidgets.QFormLayout(builder)
        form.setContentsMargins(8, 8, 8, 8)
        configure_panel_form(form)

        self.math_function = QtWidgets.QComboBox()
        for function in MATH_FUNCTIONS:
            self.math_function.addItem(function.label, function.id)
        self.math_function.currentIndexChanged.connect(function_changed)
        expand_horizontally(self.math_function)
        form.addRow(self.tr("Function"), self.math_function)

        self.math_operand_a = QtWidgets.QComboBox()
        self.math_operand_a.currentIndexChanged.connect(operand_changed)
        self.pick_operand_a = QtWidgets.QPushButton(self.tr("Pick"))
        self.pick_operand_a.setCheckable(True)
        self.pick_operand_a.setToolTip(self.tr("Click, then click a waveform trace to use it as operand A"))
        self.pick_operand_a.clicked.connect(lambda checked: start_operand_pick("a", checked))
        form.addRow(self.tr("A"), operand_picker_row(self.math_operand_a, self.pick_operand_a))

        self.math_operand_b = QtWidgets.QComboBox()
        self.math_operand_b.currentIndexChanged.connect(operand_changed)
        self.math_operand_b_label = QtWidgets.QLabel(self.tr("B"))
        self.pick_operand_b = QtWidgets.QPushButton(self.tr("Pick"))
        self.pick_operand_b.setCheckable(True)
        self.pick_operand_b.setToolTip(self.tr("Click, then click a waveform trace to use it as operand B"))
        self.pick_operand_b.clicked.connect(lambda checked: start_operand_pick("b", checked))
        self.math_operand_b_row = operand_picker_row(self.math_operand_b, self.pick_operand_b)
        form.addRow(self.math_operand_b_label, self.math_operand_b_row)

        self.math_scalar_a = QtWidgets.QLineEdit("1")
        self.math_scalar_b = QtWidgets.QLineEdit("0")
        self.math_scalar_a.textChanged.connect(operand_changed)
        self.math_scalar_b.textChanged.connect(operand_changed)
        self.math_scalar_label = QtWidgets.QLabel(self.tr("Scalars"))
        scalar_row = QtWidgets.QWidget()
        scalar_layout = QtWidgets.QHBoxLayout(scalar_row)
        scalar_layout.setContentsMargins(0, 0, 0, 0)
        scalar_layout.setSpacing(6)
        scalar_layout.addWidget(QtWidgets.QLabel(self.tr("a")))
        scalar_layout.addWidget(self.math_scalar_a)
        scalar_layout.addWidget(QtWidgets.QLabel(self.tr("b")))
        scalar_layout.addWidget(self.math_scalar_b)
        scalar_layout.setStretch(1, 1)
        scalar_layout.setStretch(3, 1)
        expand_horizontally(self.math_scalar_a)
        expand_horizontally(self.math_scalar_b)
        self.math_scalar_row = scalar_row
        form.addRow(self.math_scalar_label, self.math_scalar_row)

        self.fft_window = QtWidgets.QComboBox()
        for window in WINDOW_FUNCTIONS:
            self.fft_window.addItem(window.label, window.id)
        self.fft_window_label = QtWidgets.QLabel(self.tr("Window"))
        expand_horizontally(self.fft_window)
        form.addRow(self.fft_window_label, self.fft_window)

        self.fft_remove_dc = QtWidgets.QCheckBox(self.tr("Remove DC offset"))
        form.addRow(self.fft_remove_dc)

        self.fft_zero_pad = QtWidgets.QComboBox()
        for option_id, label in ZERO_PAD_OPTIONS:
            self.fft_zero_pad.addItem(label, option_id)
        self.fft_zero_pad.setToolTip(
            self.tr("Adds zeros after the selected waveform segment to create denser FFT bins. Does not improve true frequency resolution.")
        )
        self.fft_zero_pad_label = QtWidgets.QLabel(self.tr("Zero pad"))
        expand_horizontally(self.fft_zero_pad)
        form.addRow(self.fft_zero_pad_label, self.fft_zero_pad)

        self.math_result_name = QtWidgets.QLineEdit()
        expand_horizontally(self.math_result_name)
        form.addRow(self.tr("Name"), self.math_result_name)

        buttons = QtWidgets.QWidget()
        buttons_layout = QtWidgets.QHBoxLayout(buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        add_button = QtWidgets.QPushButton(self.tr("Add"))
        add_button.clicked.connect(add_output)
        self.update_fft_button = QtWidgets.QPushButton(self.tr("Update FFT"))
        self.update_fft_button.clicked.connect(update_fft)
        expand_horizontally(add_button)
        expand_horizontally(self.update_fft_button)
        buttons_layout.addWidget(add_button, stretch=1)
        buttons_layout.addWidget(self.update_fft_button, stretch=1)
        form.addRow(buttons)
        layout.addWidget(builder)

        self.spectrum_range_box = QtWidgets.QGroupBox(self.tr("Spectrum Range"))
        spectrum_form = QtWidgets.QFormLayout(self.spectrum_range_box)
        spectrum_form.setContentsMargins(8, 8, 8, 8)
        configure_panel_form(spectrum_form)
        self.frequency_min = QtWidgets.QLineEdit()
        self.frequency_max = QtWidgets.QLineEdit()
        apply_frequency = QtWidgets.QPushButton(self.tr("Apply Frequency Range"))
        expand_horizontally(self.frequency_min)
        expand_horizontally(self.frequency_max)
        expand_horizontally(apply_frequency)
        apply_frequency.clicked.connect(apply_frequency_range)
        spectrum_form.addRow(self.tr("Min Hz"), self.frequency_min)
        spectrum_form.addRow(self.tr("Max Hz"), self.frequency_max)
        spectrum_form.addRow(apply_frequency)
        layout.addWidget(self.spectrum_range_box)

        outputs = QtWidgets.QGroupBox(self.tr("Outputs"))
        outputs_layout = QtWidgets.QVBoxLayout(outputs)
        outputs_layout.setContentsMargins(8, 8, 8, 8)
        self.math_outputs = QtWidgets.QListWidget()
        self.math_outputs.currentTextChanged.connect(output_selected)
        self.math_outputs.itemClicked.connect(lambda item: output_selected(item.text()))
        remove_button = QtWidgets.QPushButton(self.tr("Remove"))
        expand_horizontally(remove_button)
        remove_button.clicked.connect(remove_output)
        outputs_layout.addWidget(self.math_outputs)
        outputs_layout.addWidget(remove_button)
        layout.addWidget(outputs)
        layout.addStretch()


class DetachedMeasureWindow(QtWidgets.QDialog):
    def __init__(
        self,
        *,
        channel_name: str,
        card: "MeasureChannelCard",
        reattach_callback: object,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.channel_name = channel_name
        self._card = card
        self._reattach_callback = reattach_callback
        self._reattached = False
        self.setWindowTitle(self.tr("{name} measurements").format(name=channel_name))
        self.resize(340, 360)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        card.setParent(self)
        layout.addWidget(card)
        card.show()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.reattach()
        event.accept()

    def reattach(self) -> None:
        if self._reattached:
            return
        self._reattached = True
        self.layout().removeWidget(self._card)
        self._card.hide()
        self._reattach_callback(self.channel_name)


class MeasureChannelCard(QtWidgets.QWidget):
    selected = QtCore.Signal(str)
    detachRequested = QtCore.Signal(str)
    removeRequested = QtCore.Signal(str)

    def __init__(
        self,
        channel_name: str,
        *,
        color: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.channel_name = channel_name
        self.trace_color = QtGui.QColor(color)
        if not self.trace_color.isValid():
            self.trace_color = QtGui.QColor("#808080")
        self.labels = {
            key: QtWidgets.QLabel("-")
            for key in ("max", "min", "avg", "ptp", "rms", "acrms", "period", "frequency")
        }
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.frame = QtWidgets.QFrame()
        self.frame.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.frame.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.frame.setAutoFillBackground(True)
        frame_layout = QtWidgets.QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(0, 0, 0, 10)
        frame_layout.setSpacing(8)

        self.header_frame = QtWidgets.QFrame()
        self.header_frame.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.header_frame.setAutoFillBackground(True)
        header_layout = QtWidgets.QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(10, 6, 10, 6)
        self.title_label = QtWidgets.QLabel(channel_name)
        title_font = self.title_label.font()
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        frame_layout.addWidget(self.header_frame)
        frame_layout.addWidget(horizontal_separator())
        frame_layout.addWidget(
            self._measure_group(
                self.tr("Vertical"),
                [
                    (self.tr("Max"), "max"),
                    (self.tr("Min"), "min"),
                    (self.tr("Avg"), "avg"),
                    (self.tr("Peak to peak"), "ptp"),
                    (self.tr("RMS"), "rms"),
                    (self.tr("ACRMS"), "acrms"),
                ],
            )
        )
        frame_layout.addWidget(horizontal_separator())
        frame_layout.addWidget(self._measure_group(self.tr("Horizontal"), [(self.tr("Period"), "period"), (self.tr("Frequency"), "frequency")]))
        layout.addWidget(self.frame)
        self.set_selected(False)

    def set_selected(self, selected: bool) -> None:
        palette = self.frame.palette()
        header_palette = self.header_frame.palette()
        role = QtGui.QPalette.ColorRole.Window
        base_color = self.palette().color(role)
        selected_color = blend_colors(blend_colors(base_color, self.trace_color, 0.24), QtGui.QColor("#000000"), 0.32)
        palette.setColor(role, selected_color if selected else base_color)
        self.frame.setPalette(palette)
        header_palette.setColor(role, blend_colors(self.trace_color, QtGui.QColor("#000000"), 0.45 if selected else 0.25))
        header_palette.setColor(QtGui.QPalette.ColorRole.WindowText, contrasting_text_color(header_palette.color(role)))
        self.header_frame.setPalette(header_palette)

    def set_measurements(self, measurements: dict[str, float | None], *, unit: str | None, scale: object) -> None:
        for key, label in self.labels.items():
            value_unit = unit
            if key == "period":
                value_unit = "s"
            elif key == "frequency":
                value_unit = "Hz"
            text = format_scaled_value(measurements.get(key), value_unit, scale)
            if label.text() != text:
                label.setText(text)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.selected.emit(self.channel_name)
        elif event.button() == QtCore.Qt.MouseButton.RightButton:
            self.removeRequested.emit(self.channel_name)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.selected.emit(self.channel_name)
            self.detachRequested.emit(self.channel_name)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _measure_group(self, title: str, rows: list[tuple[str, str]]) -> QtWidgets.QFrame:
        box = QtWidgets.QFrame()
        box.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        layout = QtWidgets.QVBoxLayout(box)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(4)
        title_label = QtWidgets.QLabel(title)
        title_font = title_label.font()
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        grid_widget = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        for row, (label, key) in enumerate(rows):
            name_label = QtWidgets.QLabel(label)
            value_label = self.labels[key]
            value_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            value_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            value_label.setMinimumWidth(110)
            value_label.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont))
            grid.addWidget(name_label, row, 0)
            grid.addWidget(value_label, row, 1)
        grid.setColumnStretch(1, 1)
        layout.addWidget(grid_widget)
        return box


class MeasurePanel(QtWidgets.QWidget):
    def __init__(
        self,
        *,
        measure_channel_changed: object,
        measure_property_changed: object,
        start_measure_pick: object,
        add_measure_channel: object,
        remove_measure_channel: object,
        detach_measure_channel: object,
        select_measure_channel: object,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        controls = QtWidgets.QGroupBox(self.tr("Measure"))
        form = QtWidgets.QFormLayout(controls)
        form.setContentsMargins(8, 8, 8, 8)
        configure_panel_form(form)
        self.measure_channel = QtWidgets.QComboBox()
        self.measure_channel.currentTextChanged.connect(measure_channel_changed)
        self.pick_measure_channel = QtWidgets.QPushButton(self.tr("Pick"))
        self.pick_measure_channel.setCheckable(True)
        self.pick_measure_channel.setToolTip(self.tr("Click, then click a waveform trace to measure it"))
        self.pick_measure_channel.clicked.connect(lambda checked: start_measure_pick(checked))
        self.measure_range = QtWidgets.QComboBox()
        self.measure_range.addItem(self.tr("Full waveform"), "full")
        self.measure_range.addItem(self.tr("Between X cursors"), "cursors")
        self.measure_range.currentIndexChanged.connect(measure_property_changed)
        self.measure_scale = scale_selector(self)
        self.measure_scale.currentIndexChanged.connect(measure_property_changed)
        add_button = QtWidgets.QPushButton(self.tr("Add"))
        remove_button = QtWidgets.QPushButton(self.tr("Remove"))
        keep_button_to_hint(add_button)
        keep_button_to_hint(remove_button)
        add_button.clicked.connect(add_measure_channel)
        remove_button.clicked.connect(remove_measure_channel)
        buttons = QtWidgets.QWidget()
        buttons_layout = QtWidgets.QHBoxLayout(buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(6)
        buttons_layout.addWidget(add_button)
        buttons_layout.addWidget(remove_button)
        buttons_layout.addStretch()
        expand_horizontally(self.measure_range)
        form.addRow(self.tr("Waveform"), operand_picker_row(self.measure_channel, self.pick_measure_channel))
        form.addRow(self.tr("Range"), self.measure_range)
        form.addRow(self.tr("Scale"), self.measure_scale)
        form.addRow(buttons)
        layout.addWidget(controls)

        self.measure_cards: dict[str, MeasureChannelCard] = {}
        self._detach_measure_channel = detach_measure_channel
        self._remove_measure_channel = remove_measure_channel
        self._select_measure_channel = select_measure_channel
        self.cards_widget = QtWidgets.QWidget()
        self.cards_layout = QtWidgets.QVBoxLayout(self.cards_widget)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(10)
        self.empty_measure_label = QtWidgets.QLabel(self.tr("Add waveforms to show measurements."))
        self.empty_measure_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.cards_layout.addWidget(self.empty_measure_label)
        self.cards_layout.addStretch()
        outputs = QtWidgets.QGroupBox(self.tr("Outputs"))
        outputs_layout = QtWidgets.QVBoxLayout(outputs)
        outputs_layout.setContentsMargins(8, 8, 8, 8)
        cards_scroll = QtWidgets.QScrollArea()
        cards_scroll.setWidgetResizable(True)
        cards_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        cards_scroll.setWidget(self.cards_widget)
        outputs_layout.addWidget(cards_scroll)
        layout.addWidget(outputs, stretch=1)

    def ensure_card(self, channel_name: str, *, color: str | None = None) -> MeasureChannelCard:
        card = self.measure_cards.get(channel_name)
        if card is not None:
            return card
        card = MeasureChannelCard(channel_name, color=color or "#808080")
        card.selected.connect(self._select_measure_channel)
        card.detachRequested.connect(self._detach_measure_channel)
        card.removeRequested.connect(self._remove_measure_channel)
        self.measure_cards[channel_name] = card
        self.cards_layout.insertWidget(max(self.cards_layout.count() - 1, 0), card)
        self._sync_empty_label()
        return card

    def remove_card(self, channel_name: str) -> MeasureChannelCard | None:
        card = self.measure_cards.pop(channel_name, None)
        if card is None:
            return None
        self.cards_layout.removeWidget(card)
        card.hide()
        self._sync_empty_label()
        return card

    def reattach_card(self, channel_name: str, card: MeasureChannelCard) -> None:
        self.measure_cards[channel_name] = card
        card.setParent(self.cards_widget)
        self.cards_layout.insertWidget(max(self.cards_layout.count() - 1, 0), card)
        card.show()
        self._sync_empty_label()

    def set_selected_card(self, channel_name: str | None) -> None:
        for name, card in self.measure_cards.items():
            card.set_selected(name == channel_name)

    def _sync_empty_label(self) -> None:
        self.empty_measure_label.setVisible(not self.measure_cards)
