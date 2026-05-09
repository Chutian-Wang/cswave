from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

import numpy as np

from csv_loader import ChannelData, OSCILLOSCOPE_COLORS, WaveformData, excel_sheet_names, load_waveform
from math_engine import (
    MATH_FUNCTIONS,
    MATH_FUNCTION_BY_ID,
    WINDOW_FUNCTIONS,
    ZERO_PAD_OPTIONS,
    SpectrumData,
    create_calculated_channel,
    create_fft_spectrum,
    default_result_name,
)
from PySide6 import QtCore, QtGui, QtWidgets
from app_theme import apply_dark_theme, apply_system_theme
from plot_widgets import AxisGroupSettings, SpectrumPlot, WaveformPlot


def _viewer_tr(text: str) -> str:
    return QtCore.QCoreApplication.translate("viewer", text)


@dataclass(frozen=True)
class TimebaseSettings:
    kind: str
    column: str | None = None
    value: float | None = None


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


def _operand_picker_row(combo: QtWidgets.QComboBox, button: QtWidgets.QPushButton) -> QtWidgets.QWidget:
    row = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    layout.addWidget(combo, stretch=1)
    layout.addWidget(button)
    return row


class ChannelsPanel(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.channel_layout = QtWidgets.QVBoxLayout(self)
        self.channel_layout.setContentsMargins(8, 8, 8, 8)
        self.channel_layout.setSpacing(6)
        self.channel_layout.addStretch()


class CursorPanel(QtWidgets.QWidget):
    def __init__(
        self,
        *,
        x_cursor_toggle: QtWidgets.QCheckBox,
        y_cursor_toggle: QtWidgets.QCheckBox,
        cursor_axis_selector: QtWidgets.QComboBox,
        active_channel: QtWidgets.QComboBox,
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
        reset_cursors.clicked.connect(reset_callback)
        controls_layout.addWidget(reset_cursors, 1, 0, 1, 2)
        controls_layout.addWidget(QtWidgets.QLabel(self.tr("Cursor group")), 2, 0)
        controls_layout.addWidget(cursor_axis_selector, 2, 1)
        controls_layout.addWidget(QtWidgets.QLabel(self.tr("Active channel")), 3, 0)
        controls_layout.addWidget(active_channel, 3, 1)
        controls_layout.setColumnStretch(1, 1)
        layout.addWidget(controls)

        layout.addWidget(self._value_group(self.tr("X Positions"), [(self.tr("X1"), "X1"), (self.tr("X2"), "X2"), (self.tr("Delta X"), "dX")]))
        layout.addWidget(self._value_group(self.tr("Y Positions"), [(self.tr("Y1"), "Y1"), (self.tr("Y2"), "Y2"), (self.tr("Delta Y"), "dY")]))
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

        self.math_function = QtWidgets.QComboBox()
        for function in MATH_FUNCTIONS:
            self.math_function.addItem(function.label, function.id)
        self.math_function.currentIndexChanged.connect(function_changed)
        form.addRow(self.tr("Function"), self.math_function)

        self.math_operand_a = QtWidgets.QComboBox()
        self.math_operand_a.currentIndexChanged.connect(operand_changed)
        self.pick_operand_a = QtWidgets.QPushButton(self.tr("Pick"))
        self.pick_operand_a.setCheckable(True)
        self.pick_operand_a.setToolTip(self.tr("Click, then click a waveform trace to use it as operand A"))
        self.pick_operand_a.clicked.connect(lambda checked: start_operand_pick("a", checked))
        form.addRow(self.tr("A"), _operand_picker_row(self.math_operand_a, self.pick_operand_a))

        self.math_operand_b = QtWidgets.QComboBox()
        self.math_operand_b.currentIndexChanged.connect(operand_changed)
        self.math_operand_b_label = QtWidgets.QLabel(self.tr("B"))
        self.pick_operand_b = QtWidgets.QPushButton(self.tr("Pick"))
        self.pick_operand_b.setCheckable(True)
        self.pick_operand_b.setToolTip(self.tr("Click, then click a waveform trace to use it as operand B"))
        self.pick_operand_b.clicked.connect(lambda checked: start_operand_pick("b", checked))
        self.math_operand_b_row = _operand_picker_row(self.math_operand_b, self.pick_operand_b)
        form.addRow(self.math_operand_b_label, self.math_operand_b_row)

        self.fft_window = QtWidgets.QComboBox()
        for window in WINDOW_FUNCTIONS:
            self.fft_window.addItem(window.label, window.id)
        self.fft_window_label = QtWidgets.QLabel(self.tr("Window"))
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
        form.addRow(self.fft_zero_pad_label, self.fft_zero_pad)

        self.math_result_name = QtWidgets.QLineEdit()
        form.addRow(self.tr("Name"), self.math_result_name)

        buttons = QtWidgets.QWidget()
        buttons_layout = QtWidgets.QHBoxLayout(buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        add_button = QtWidgets.QPushButton(self.tr("Add"))
        add_button.clicked.connect(add_output)
        self.update_fft_button = QtWidgets.QPushButton(self.tr("Update FFT"))
        self.update_fft_button.clicked.connect(update_fft)
        buttons_layout.addWidget(add_button)
        buttons_layout.addWidget(self.update_fft_button)
        form.addRow(buttons)
        layout.addWidget(builder)

        self.spectrum_range_box = QtWidgets.QGroupBox(self.tr("Spectrum Range"))
        spectrum_form = QtWidgets.QFormLayout(self.spectrum_range_box)
        spectrum_form.setContentsMargins(8, 8, 8, 8)
        self.frequency_min = QtWidgets.QLineEdit()
        self.frequency_max = QtWidgets.QLineEdit()
        apply_frequency = QtWidgets.QPushButton(self.tr("Apply Frequency Range"))
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
        remove_button.clicked.connect(remove_output)
        outputs_layout.addWidget(self.math_outputs)
        outputs_layout.addWidget(remove_button)
        layout.addWidget(outputs)
        layout.addStretch()


class MeasurePanel(QtWidgets.QWidget):
    def __init__(
        self,
        *,
        update_measurements: object,
        start_measure_pick: object,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        controls = QtWidgets.QGroupBox(self.tr("Measure"))
        form = QtWidgets.QFormLayout(controls)
        form.setContentsMargins(8, 8, 8, 8)
        self.measure_channel = QtWidgets.QComboBox()
        self.measure_channel.currentIndexChanged.connect(update_measurements)
        self.pick_measure_channel = QtWidgets.QPushButton(self.tr("Pick"))
        self.pick_measure_channel.setCheckable(True)
        self.pick_measure_channel.setToolTip(self.tr("Click, then click a waveform trace to measure it"))
        self.pick_measure_channel.clicked.connect(lambda checked: start_measure_pick(checked))
        self.measure_range = QtWidgets.QComboBox()
        self.measure_range.addItem(self.tr("Full waveform"), "full")
        self.measure_range.addItem(self.tr("Between X cursors"), "cursors")
        self.measure_range.currentIndexChanged.connect(update_measurements)
        form.addRow(self.tr("Waveform"), _operand_picker_row(self.measure_channel, self.pick_measure_channel))
        form.addRow(self.tr("Range"), self.measure_range)
        layout.addWidget(controls)

        self.measure_labels = {
            key: QtWidgets.QLabel("-")
            for key in ("max", "min", "avg", "ptp", "rms", "acrms", "period", "frequency")
        }
        layout.addWidget(
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
        layout.addWidget(self._measure_group(self.tr("Horizontal"), [(self.tr("Period"), "period"), (self.tr("Frequency"), "frequency")]))
        layout.addStretch()

    def _measure_group(self, title: str, rows: list[tuple[str, str]]) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox(title)
        grid = QtWidgets.QGridLayout(box)
        grid.setContentsMargins(8, 8, 8, 8)
        for row, (label, key) in enumerate(rows):
            name_label = QtWidgets.QLabel(label)
            value_label = self.measure_labels[key]
            value_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            value_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            value_label.setMinimumWidth(110)
            value_label.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont))
            grid.addWidget(name_label, row, 0)
            grid.addWidget(value_label, row, 1)
        grid.setColumnStretch(1, 1)
        return box


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, *, startup_language: str = "system") -> None:
        super().__init__()
        self.setWindowTitle("cswave")
        self.resize(1280, 820)
        self.startup_language = _normalized_startup_language(startup_language)
        self.data: WaveformData | None = None
        self.source_data: WaveformData | None = None
        self.calculated_channels: list[ChannelData] = []
        self.spectra: dict[str, SpectrumData] = {}
        self.channel_checks: dict[str, QtWidgets.QCheckBox] = {}
        self.last_cursor_channel_by_group: dict[str, str] = {}
        self.pending_waveform_pick: str | None = None
        self._waveform_setup_pending = False

        self.waveform_plot = WaveformPlot()
        self.spectrum_plot = SpectrumPlot()
        self.waveform_plot.cursorChanged.connect(self._waveform_cursors_changed)
        self.waveform_plot.activeAxisGroupChanged.connect(self._sync_axis_group_selector)
        self.waveform_plot.traceClicked.connect(self._waveform_picked)

        self.channel_panel = ChannelsPanel()
        self.channel_layout = self.channel_panel.channel_layout

        self.active_channel = QtWidgets.QComboBox()
        self.cursor_axis_selector = QtWidgets.QComboBox()
        self.cursor_axis_selector.addItem(self.tr("Left"), "left")
        self.cursor_axis_selector.addItem(self.tr("Right"), "right")
        self.cursor_axis_selector.currentIndexChanged.connect(lambda _index: self._cursor_axis_changed(self.cursor_axis_selector.currentData()))
        self.x_cursor_toggle = QtWidgets.QCheckBox(self.tr("X cursors"))
        self.y_cursor_toggle = QtWidgets.QCheckBox(self.tr("Y cursors"))
        self.x_cursor_toggle.toggled.connect(self._set_x_cursors_visible)
        self.y_cursor_toggle.toggled.connect(self._set_y_cursors_visible)
        self.active_channel.currentTextChanged.connect(self._active_channel_changed)

        cursor_panel = CursorPanel(
            x_cursor_toggle=self.x_cursor_toggle,
            y_cursor_toggle=self.y_cursor_toggle,
            cursor_axis_selector=self.cursor_axis_selector,
            active_channel=self.active_channel,
            reset_callback=self._reset_cursors,
        )
        self.cursor_labels = cursor_panel.cursor_labels
        math_panel = MathPanel(
            operand_changed=self._math_operand_changed,
            function_changed=self._math_function_changed,
            start_operand_pick=self._start_operand_pick,
            add_output=self._add_math_output,
            update_fft=self._update_fft_spectrum,
            apply_frequency_range=self._apply_frequency_range,
            output_selected=self._math_output_selected,
            remove_output=self._remove_math_output,
        )
        self.math_function = math_panel.math_function
        self.math_operand_a = math_panel.math_operand_a
        self.pick_operand_a = math_panel.pick_operand_a
        self.math_operand_b = math_panel.math_operand_b
        self.math_operand_b_label = math_panel.math_operand_b_label
        self.pick_operand_b = math_panel.pick_operand_b
        self.math_operand_b_row = math_panel.math_operand_b_row
        self.fft_window = math_panel.fft_window
        self.fft_window_label = math_panel.fft_window_label
        self.fft_remove_dc = math_panel.fft_remove_dc
        self.fft_zero_pad = math_panel.fft_zero_pad
        self.fft_zero_pad_label = math_panel.fft_zero_pad_label
        self.math_result_name = math_panel.math_result_name
        self.update_fft_button = math_panel.update_fft_button
        self.spectrum_range_box = math_panel.spectrum_range_box
        self.frequency_min = math_panel.frequency_min
        self.frequency_max = math_panel.frequency_max
        self.math_outputs = math_panel.math_outputs
        measure_panel = MeasurePanel(update_measurements=self._update_measurements, start_measure_pick=self._start_measure_pick)
        self.measure_channel = measure_panel.measure_channel
        self.pick_measure_channel = measure_panel.pick_measure_channel
        self.measure_range = measure_panel.measure_range
        self.measure_labels = measure_panel.measure_labels

        self.side_tabs = DetachableTabWidget()
        self.side_tabs.addTab(self._scroll_area(self.channel_panel), self.tr("Channels"))
        self.side_tabs.addTab(cursor_panel, self.tr("Cursors"))
        self.side_tabs.addTab(math_panel, self.tr("Math"))
        self.side_tabs.addTab(measure_panel, self.tr("Measure"))
        self.side_tabs.setMinimumWidth(260)

        self.plot_tabs = QtWidgets.QTabWidget()
        self.plot_tabs.addTab(self.waveform_plot, self.tr("Waveforms"))
        self.plot_tabs.addTab(self.spectrum_plot, self.tr("Spectrum"))

        self.splitter = QtWidgets.QSplitter()
        self.splitter.addWidget(self.plot_tabs)
        self.splitter.addWidget(self.side_tabs)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.splitterMoved.connect(self._update_side_panel_restore_tab)
        self.setCentralWidget(self.splitter)

        self.side_panel_restore_tab = VerticalTextButton(self.tr("^ Panel ^"), self)
        self.side_panel_restore_tab.setToolTip(self.tr("Restore right panel"))
        self.side_panel_restore_tab.setFixedSize(self.side_panel_restore_tab.sizeHint())
        self.side_panel_restore_tab.clicked.connect(self._restore_side_panel)
        self.side_panel_restore_tab.hide()

        self.statusBar().showMessage(self.tr("Load a waveform file to begin"))
        self._build_actions()
        self._build_shortcuts()
        self._math_function_changed()
        self._update_side_panel_restore_tab()

    def load_file(self, path: str | Path, *, sheet_name: str | None = None, show_setup: bool = False) -> None:
        selected_sheet = sheet_name
        if selected_sheet is None and Path(path).suffix.lower() in {".xls", ".xlsx", ".xlsm"}:
            selected_sheet = self._select_excel_sheet(path)
            if selected_sheet is None:
                return
        data = load_waveform(path, sheet_name=selected_sheet)
        self.source_data = data
        self.calculated_channels.clear()
        self.spectra.clear()
        self.data = data
        self.spectrum_plot.clear()
        self.waveform_plot.set_data(data)
        self._rebuild_channels(data.channels)
        self._rebuild_active_channel(data.channels)
        self._sync_math_controls()
        self._sync_measure_controls()
        self._sync_math_outputs()
        self._sync_cursor_axis_selector()
        ignored = self.tr(" Ignored {count} column(s).").format(count=len(data.ignored_columns)) if data.ignored_columns else ""
        time_source = data.time_column or self.tr("sample index")
        sheet = self.tr(", sheet: {sheet}").format(sheet=data.sheet_name) if data.sheet_name else ""
        self.statusBar().showMessage(
            self.tr("Loaded {name}{sheet}: {count} channel(s), time base: {time_source}.{ignored}").format(
                name=data.source_path.name,
                sheet=sheet,
                count=len(data.channels),
                time_source=time_source,
                ignored=ignored,
            )
        )
        self._update_cursor_panel()
        if show_setup:
            self._schedule_waveform_setup()

    def _schedule_waveform_setup(self) -> None:
        self._waveform_setup_pending = True
        QtCore.QTimer.singleShot(0, self._open_pending_waveform_setup)

    def _open_pending_waveform_setup(self) -> None:
        if not self._waveform_setup_pending:
            return
        self._waveform_setup_pending = False
        self._open_waveform_setup()

    def _build_actions(self) -> None:
        toolbar = self.addToolBar(self.tr("Main"))
        toolbar.setObjectName("MainToolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)

        toolbar.addWidget(_toolbar_section_label(self.tr("File")))

        open_action = QtGui.QAction(self.tr("Open Waveform"), self)
        open_action.setShortcut(QtGui.QKeySequence.Open)
        open_action.triggered.connect(self._open_dialog)
        toolbar.addAction(open_action)

        toolbar.addSeparator()
        toolbar.addWidget(_toolbar_section_label(self.tr("View")))

        reset_action = QtGui.QAction(self.tr("Reset View"), self)
        reset_action.triggered.connect(self._reset_active_view)
        toolbar.addAction(reset_action)

        waveform_setup_action = QtGui.QAction(self.tr("Waveform Setup..."), self)
        waveform_setup_action.setToolTip(self.tr("Configure left/right axis grouping, units, and Y ranges"))
        waveform_setup_action.triggered.connect(self._open_waveform_setup)
        toolbar.addAction(waveform_setup_action)

        toolbar.addSeparator()
        toolbar.addWidget(_toolbar_section_label(self.tr("Navigate")))
        toolbar.addWidget(_toolbar_field_label(self.tr("Y group")))
        self.axis_group_selector = QtWidgets.QComboBox()
        self.axis_group_selector.addItem(self.tr("Left"), "left")
        self.axis_group_selector.addItem(self.tr("Right"), "right")
        self.axis_group_selector.setToolTip(self.tr("Active Y axis group for Y pan and zoom"))
        self.axis_group_selector.setMinimumContentsLength(5)
        self._sync_axis_group_selector()
        self.axis_group_selector.currentIndexChanged.connect(self._axis_group_changed)
        toolbar.addWidget(self.axis_group_selector)

        toolbar.addWidget(_toolbar_field_label(self.tr("Zoom")))
        self.zoom_axis_selector = QtWidgets.QComboBox()
        self.zoom_axis_selector.addItems(["X", "Y"])
        self.zoom_axis_selector.setToolTip(self.tr("Axis used by toolbar zoom buttons"))
        self.zoom_axis_selector.setMinimumContentsLength(1)
        toolbar.addWidget(self.zoom_axis_selector)

        zoom_in_action = QtGui.QAction("+", self)
        zoom_in_action.setToolTip(self.tr("Zoom in on the selected axis"))
        zoom_in_action.triggered.connect(lambda: self.waveform_plot.zoom_in(self._selected_zoom_axis()))
        toolbar.addAction(zoom_in_action)

        zoom_out_action = QtGui.QAction("-", self)
        zoom_out_action.setToolTip(self.tr("Zoom out on the selected axis"))
        zoom_out_action.triggered.connect(lambda: self.waveform_plot.zoom_out(self._selected_zoom_axis()))
        toolbar.addAction(zoom_out_action)

        toolbar.addSeparator()
        toolbar.addWidget(_toolbar_section_label(self.tr("Display")))
        toolbar.addWidget(_toolbar_field_label(self.tr("Renderer")))
        self.renderer_selector = QtWidgets.QComboBox()
        self.renderer_selector.addItem("CPU", "cpu")
        self.renderer_selector.addItem("OpenGL", "opengl")
        self.renderer_selector.setToolTip(self.tr("Rendering backend for waveform drawing"))
        self.renderer_selector.setMinimumContentsLength(6)
        self._sync_renderer_selector()
        self.renderer_selector.currentIndexChanged.connect(self._renderer_changed)
        toolbar.addWidget(self.renderer_selector)
        self.force_dark_mode = QtWidgets.QCheckBox(self.tr("Force dark"))
        self.force_dark_mode.setToolTip(self.tr("Use a dark application theme instead of the system theme"))
        self.force_dark_mode.toggled.connect(self._force_dark_mode_changed)
        toolbar.addWidget(self.force_dark_mode)
        toolbar.addWidget(_toolbar_field_label(self.tr("Language")))
        self.language_selector = QtWidgets.QComboBox()
        self.language_selector.addItem("System", "system")
        self.language_selector.addItem("English", "en")
        self.language_selector.addItem("中文", "zh_CN")
        self.language_selector.addItem("日本語", "ja_JP")
        self.language_selector.setToolTip(self.tr("Change the startup language and restart the app"))
        self.language_selector.setMinimumContentsLength(8)
        self._sync_language_selector()
        self.language_selector.currentIndexChanged.connect(self._language_changed)
        toolbar.addWidget(self.language_selector)

    def _open_dialog(self) -> None:
        path, _selected_filter = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tr("Open Waveform"),
            str(Path.cwd()),
            self.tr("Waveform files (*.csv *.xls *.xlsx *.xlsm);;CSV files (*.csv);;Excel files (*.xls *.xlsx *.xlsm);;All files (*)"),
        )
        if not path:
            return
        try:
            self.load_file(path, show_setup=True)
        except Exception as exc:  # noqa: BLE001 - GUI needs user-facing failure.
            QtWidgets.QMessageBox.critical(self, self.tr("Could not load waveform"), str(exc))

    def _select_excel_sheet(self, path: str | Path) -> str | None:
        sheets = excel_sheet_names(path)
        if not sheets:
            return None
        if len(sheets) == 1:
            return sheets[0]
        sheet, accepted = QtWidgets.QInputDialog.getItem(
            self,
            self.tr("Select Waveform Sheet"),
            self.tr("Waveform sheet"),
            sheets,
            0,
            False,
        )
        return sheet if accepted and sheet else None

    def _selected_zoom_axis(self) -> str:
        return self.zoom_axis_selector.currentText().lower()

    def _reset_active_view(self) -> None:
        if self.plot_tabs.currentWidget() is self.spectrum_plot:
            self.spectrum_plot.reset_view()
            return
        self.waveform_plot.reset_view()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._position_side_panel_restore_tab()

    def _restore_side_panel(self) -> None:
        width = max(self.splitter.width(), 1)
        panel_width = min(320, max(260, width // 4))
        self.splitter.setSizes([max(width - panel_width, 1), panel_width])
        self._update_side_panel_restore_tab()

    def _update_side_panel_restore_tab(self, *_args: object) -> None:
        if not hasattr(self, "side_panel_restore_tab"):
            return
        sizes = self.splitter.sizes()
        layout_ready = len(sizes) > 1 and sum(sizes) > 0 and self.splitter.isVisible()
        hidden = layout_ready and sizes[1] <= 8
        self.side_panel_restore_tab.setVisible(hidden)
        if hidden:
            self._position_side_panel_restore_tab()
            self.side_panel_restore_tab.raise_()

    def _position_side_panel_restore_tab(self) -> None:
        if not hasattr(self, "side_panel_restore_tab"):
            return
        margin = 0
        x = max(self.width() - self.side_panel_restore_tab.width() - margin, 0)
        available_height = max(self.height() - self.statusBar().height(), self.side_panel_restore_tab.height())
        y = max((available_height - self.side_panel_restore_tab.height()) // 4, 32)
        self.side_panel_restore_tab.move(x, y)

    def _sync_axis_group_selector(self, *_args: object) -> None:
        current_index = self.axis_group_selector.findData(self.waveform_plot.active_y_group)
        if current_index < 0:
            return
        self.axis_group_selector.blockSignals(True)
        self.axis_group_selector.setCurrentIndex(current_index)
        self.axis_group_selector.blockSignals(False)

    def _axis_group_changed(self) -> None:
        group = self.axis_group_selector.currentData()
        if group not in {"left", "right"}:
            return
        self.waveform_plot.set_active_y_group(group)
        axis = self.tr("Left") if self.waveform_plot.active_y_group == "left" else self.tr("Right")
        self.statusBar().showMessage(self.tr("Y control group: {axis} axis").format(axis=axis))

    def _sync_renderer_selector(self) -> None:
        opengl_index = self.renderer_selector.findData("opengl")
        if opengl_index >= 0:
            item = self.renderer_selector.model().item(opengl_index)
            if item is not None:
                item.setEnabled(self.waveform_plot.opengl_available)
            self.renderer_selector.setItemData(
                opengl_index,
                self.tr("Use OpenGL rendering") if self.waveform_plot.opengl_available else self.tr("OpenGL is not available"),
                QtCore.Qt.ItemDataRole.ToolTipRole,
            )
        current_index = self.renderer_selector.findData(self.waveform_plot.renderer_mode)
        if current_index >= 0:
            self.renderer_selector.blockSignals(True)
            self.renderer_selector.setCurrentIndex(current_index)
            self.renderer_selector.blockSignals(False)

    def _renderer_changed(self) -> None:
        mode = self.renderer_selector.currentData()
        if mode not in {"cpu", "opengl"}:
            return
        if self.waveform_plot.set_renderer_mode(mode):
            self.statusBar().showMessage(self.tr("Renderer: {renderer}").format(renderer=self.renderer_selector.currentText()))
            self._sync_renderer_selector()
            return
        self._sync_renderer_selector()
        QtWidgets.QMessageBox.warning(self, self.tr("Renderer unavailable"), self.tr("OpenGL rendering is not available on this system."))

    def _force_dark_mode_changed(self, enabled: bool) -> None:
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        if enabled:
            apply_dark_theme(app)
        else:
            apply_system_theme(app)

    def _sync_language_selector(self) -> None:
        if not hasattr(self, "language_selector"):
            return
        index = self.language_selector.findData(self.startup_language)
        if index < 0:
            index = self.language_selector.findData("system")
        self.language_selector.blockSignals(True)
        self.language_selector.setCurrentIndex(max(index, 0))
        self.language_selector.blockSignals(False)

    def _language_changed(self) -> None:
        language = self.language_selector.currentData()
        if language == self.startup_language:
            return
        answer = QtWidgets.QMessageBox.question(
            self,
            self.tr("Restart Required"),
            self.tr("Restart now to apply the selected language?"),
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.Yes,
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            self._sync_language_selector()
            return
        self._restart_with_language(language)

    def _restart_with_language(self, language: str) -> None:
        arguments = [str(Path(sys.argv[0]).resolve()), "--language", language]
        if self.source_data is not None:
            arguments.append(str(self.source_data.source_path))
        if QtCore.QProcess.startDetached(sys.executable, arguments):
            QtWidgets.QApplication.quit()
            return
        QtWidgets.QMessageBox.warning(self, self.tr("Restart Failed"), self.tr("Could not restart the application."))
        self._sync_language_selector()

    def _build_shortcuts(self) -> None:
        toggle_axis = QtGui.QShortcut(QtGui.QKeySequence("T"), self)
        toggle_axis.activated.connect(self._toggle_axis_group)
        reset_view = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+R"), self)
        reset_view.activated.connect(self._reset_active_view)
        reset_cursors = QtGui.QShortcut(QtGui.QKeySequence("Shift+R"), self)
        reset_cursors.activated.connect(self._reset_cursors)
        toggle_x_cursors = QtGui.QShortcut(QtGui.QKeySequence("X"), self)
        toggle_x_cursors.activated.connect(self._toggle_x_cursors)
        toggle_y_cursors = QtGui.QShortcut(QtGui.QKeySequence("Y"), self)
        toggle_y_cursors.activated.connect(self._toggle_y_cursors)

    def _toggle_axis_group(self) -> None:
        self.waveform_plot.toggle_active_y_group()
        self._sync_axis_group_selector()
        axis = self.tr("Left") if self.waveform_plot.active_y_group == "left" else self.tr("Right")
        self.statusBar().showMessage(self.tr("Y control group: {axis} axis").format(axis=axis))

    def _toggle_x_cursors(self) -> None:
        self.x_cursor_toggle.setChecked(not self.x_cursor_toggle.isChecked())

    def _toggle_y_cursors(self) -> None:
        self.y_cursor_toggle.setChecked(not self.y_cursor_toggle.isChecked())

    def _open_waveform_setup(self) -> None:
        if self.data is None:
            QtWidgets.QMessageBox.information(self, self.tr("Waveform Setup"), self.tr("Load a waveform file before configuring axes."))
            return
        dialog = WaveformSetupDialog(self.data, self.waveform_plot.axis_settings, self.waveform_plot.group_defaults(), self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        self._apply_timebase_settings(dialog.timebase_settings())
        self.waveform_plot.update_axis_settings(self._settings_for_current_channels(dialog.settings()))
        self._sync_channel_checks()
        self._rebuild_active_channel(self.data.channels)
        self._update_cursor_panel()

    def _open_axis_setup(self) -> None:
        self._open_waveform_setup()

    def _rebuild_channels(self, channels: list[ChannelData]) -> None:
        while self.channel_layout.count() > 1:
            item = self.channel_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.channel_checks.clear()

        for channel in channels:
            checkbox = QtWidgets.QCheckBox(channel.name)
            checkbox.setChecked(channel.name in self.waveform_plot.selected_channels)
            checkbox.setEnabled(self.waveform_plot.axis_settings.get(channel.name, AxisGroupSettings("disabled", "")).group != "disabled")
            checkbox.setToolTip(self._channel_checkbox_tooltip(channel.name))
            checkbox.toggled.connect(self._channel_selection_changed)
            checkbox.setStyleSheet(f"QCheckBox {{ color: {channel.color}; }}")
            self.channel_checks[channel.name] = checkbox
            self.channel_layout.insertWidget(self.channel_layout.count() - 1, checkbox)

    def _sync_channel_checks(self) -> None:
        for name, checkbox in self.channel_checks.items():
            disabled = self.waveform_plot.axis_settings.get(name, AxisGroupSettings("disabled", "")).group == "disabled"
            checkbox.blockSignals(True)
            checkbox.setEnabled(not disabled)
            checkbox.setChecked(not disabled and name in self.waveform_plot.selected_channels)
            checkbox.setToolTip(self._channel_checkbox_tooltip(name))
            checkbox.blockSignals(False)

    def _channel_checkbox_tooltip(self, name: str) -> str:
        setting = self.waveform_plot.axis_settings.get(name)
        if setting is not None and setting.group == "disabled":
            return self.tr("Disabled in Waveform Setup")
        return self.tr("Show or hide this enabled waveform")

    def _rebuild_active_channel(self, channels: list[ChannelData]) -> None:
        previous = self.active_channel.currentText()
        if previous:
            self.last_cursor_channel_by_group[self.waveform_plot.cursor_axis_group] = previous
        candidates = [
            channel.name for channel in channels
            if self.waveform_plot.axis_settings[channel.name].group == self.waveform_plot.cursor_axis_group
            and channel.name in self.waveform_plot.selected_channels
        ]
        remembered = self.last_cursor_channel_by_group.get(self.waveform_plot.cursor_axis_group)
        self.active_channel.blockSignals(True)
        self.active_channel.clear()
        self.active_channel.addItems(candidates)
        if remembered in candidates:
            self.active_channel.setCurrentText(remembered)
        elif candidates:
            self.last_cursor_channel_by_group[self.waveform_plot.cursor_axis_group] = candidates[0]
        self.active_channel.blockSignals(False)

    def _channel_selection_changed(self) -> None:
        selected = {
            name
            for name, checkbox in self.channel_checks.items()
            if checkbox.isChecked()
        }
        self.waveform_plot.set_selected_channels(selected)
        if self.data is not None:
            self._rebuild_active_channel(self.data.channels)
        self._update_cursor_panel()

    def _set_x_cursors_visible(self, visible: bool) -> None:
        self.waveform_plot.set_x_cursors_visible(visible)
        self._update_cursor_panel()

    def _set_y_cursors_visible(self, visible: bool) -> None:
        self.waveform_plot.set_y_cursors_visible(visible)
        self._sync_cursor_axis_selector()
        if self.data is not None:
            self._rebuild_active_channel(self.data.channels)
        self._update_cursor_panel()

    def _reset_cursors(self) -> None:
        self.waveform_plot.reset_cursors_to_active_group_center()
        self.x_cursor_toggle.blockSignals(True)
        self.y_cursor_toggle.blockSignals(True)
        self.x_cursor_toggle.setChecked(True)
        self.y_cursor_toggle.setChecked(True)
        self.x_cursor_toggle.blockSignals(False)
        self.y_cursor_toggle.blockSignals(False)
        self.waveform_plot.set_x_cursors_visible(True)
        self.waveform_plot.set_y_cursors_visible(True)
        self._sync_cursor_axis_selector()
        if self.data is not None:
            self._rebuild_active_channel(self.data.channels)
        self._update_cursor_panel()

    def _cursor_axis_changed(self, group: str) -> None:
        if group not in {"left", "right"}:
            return
        previous = self.active_channel.currentText()
        if previous:
            self.last_cursor_channel_by_group[self.waveform_plot.cursor_axis_group] = previous
        self.waveform_plot.set_cursor_axis_group(group, preserve_visual_position=True)
        if self.data is not None:
            self._rebuild_active_channel(self.data.channels)
        self._update_cursor_panel()

    def _active_channel_changed(self, channel_name: str) -> None:
        if channel_name:
            self.last_cursor_channel_by_group[self.waveform_plot.cursor_axis_group] = channel_name
        self._update_cursor_panel()

    def _sync_cursor_axis_selector(self) -> None:
        self.cursor_axis_selector.blockSignals(True)
        index = self.cursor_axis_selector.findData(self.waveform_plot.cursor_axis_group)
        if index >= 0:
            self.cursor_axis_selector.setCurrentIndex(index)
        self.cursor_axis_selector.blockSignals(False)

    def _update_cursor_panel(self, *_args: object) -> None:
        values = self.waveform_plot.cursor_values(self.active_channel.currentText() or None)
        mapping = {
            "X1": values.get("x1"),
            "X2": values.get("x2"),
            "dX": values.get("dx"),
            "Y1": values.get("y1"),
            "Y2": values.get("y2"),
            "dY": values.get("dy"),
            "Active Y1": values.get("active_y1"),
            "Active Y2": values.get("active_y2"),
            "Active dY": values.get("active_dy"),
        }
        for key, value in mapping.items():
            self.cursor_labels[key].setText(_format_value(value))

    def _waveform_cursors_changed(self, *_args: object) -> None:
        self._update_cursor_panel()
        if hasattr(self, "measure_range") and self.measure_range.currentData() == "cursors":
            self._update_measurements()

    def _sync_math_controls(self) -> None:
        current_a = self.math_operand_a.currentText() if hasattr(self, "math_operand_a") else ""
        current_b = self.math_operand_b.currentText() if hasattr(self, "math_operand_b") else ""
        names = [channel.name for channel in self.data.channels] if self.data is not None else []
        for combo, current in ((self.math_operand_a, current_a), (self.math_operand_b, current_b)):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(names)
            if current in names:
                combo.setCurrentText(current)
            combo.blockSignals(False)
        self._math_function_changed()
        self._sync_measure_controls()

    def _sync_math_outputs(self) -> None:
        if not hasattr(self, "math_outputs"):
            return
        current = self.math_outputs.currentItem().text() if self.math_outputs.currentItem() is not None else ""
        self.math_outputs.blockSignals(True)
        self.math_outputs.clear()
        for channel in self.calculated_channels:
            self.math_outputs.addItem(channel.name)
        for name in self.spectra:
            self.math_outputs.addItem(name)
        matching = self.math_outputs.findItems(current, QtCore.Qt.MatchFlag.MatchExactly)
        if matching:
            self.math_outputs.setCurrentItem(matching[0])
        self.math_outputs.blockSignals(False)

    def _math_function_changed(self) -> None:
        function_id = self.math_function.currentData() if hasattr(self, "math_function") else None
        function = MATH_FUNCTION_BY_ID.get(function_id)
        is_binary = function is not None and function.arity == 2
        is_fft = function is not None and function.domain == "frequency"
        self.math_operand_b.setEnabled(is_binary)
        self.math_operand_b_row.setVisible(is_binary)
        self.math_operand_b_label.setVisible(is_binary)
        self.pick_operand_b.setVisible(is_binary)
        if not is_binary and self.pending_waveform_pick == "math_b":
            self._clear_operand_pick()
        self.fft_window.setEnabled(is_fft)
        self.fft_window.setVisible(is_fft)
        self.fft_window_label.setVisible(is_fft)
        self.fft_remove_dc.setVisible(is_fft)
        self.fft_zero_pad.setVisible(is_fft)
        self.fft_zero_pad_label.setVisible(is_fft)
        self.update_fft_button.setVisible(is_fft)
        if hasattr(self, "spectrum_range_box"):
            self.spectrum_range_box.setVisible(is_fft)
        self._math_operand_changed()

    def _sync_measure_controls(self) -> None:
        if not hasattr(self, "measure_channel"):
            return
        current = self.measure_channel.currentText()
        names = [channel.name for channel in self.data.channels] if self.data is not None else []
        self.measure_channel.blockSignals(True)
        self.measure_channel.clear()
        self.measure_channel.addItems(names)
        if current in names:
            self.measure_channel.setCurrentText(current)
        self.measure_channel.blockSignals(False)
        self._update_measurements()

    def _update_measurements(self, *_args: object) -> None:
        if not hasattr(self, "measure_labels"):
            return
        channel = self._channel_by_name(self.measure_channel.currentText()) if self.data is not None else None
        if self.data is None or channel is None:
            self._set_measurements({})
            return

        time = self.data.time.astype(float)
        values = channel.values.astype(float)
        if self.measure_range.currentData() == "cursors":
            cursor_range = self.waveform_plot.x_cursor_range()
            if cursor_range is None:
                self._set_measurements({})
                return
            low, high = cursor_range
            mask = (time >= low) & (time <= high)
        else:
            mask = np.ones(values.size, dtype=bool)
        mask &= np.isfinite(time) & np.isfinite(values)
        selected_time = time[mask]
        selected_values = values[mask]
        if selected_values.size == 0:
            self._set_measurements({})
            return

        average = float(np.mean(selected_values))
        vertical = {
            "max": float(np.max(selected_values)),
            "min": float(np.min(selected_values)),
            "avg": average,
            "ptp": float(np.ptp(selected_values)),
            "rms": float(np.sqrt(np.mean(np.square(selected_values)))),
            "acrms": float(np.sqrt(np.mean(np.square(selected_values - average)))),
        }
        horizontal = self._fft_horizontal_measurements(channel, self.waveform_plot.x_cursor_range() if self.measure_range.currentData() == "cursors" else None)
        self._set_measurements({**vertical, **horizontal})

    def _fft_horizontal_measurements(
        self,
        channel: ChannelData,
        time_range: tuple[float, float] | None,
    ) -> dict[str, float | None]:
        if self.data is None:
            return {"frequency": None, "period": None}
        try:
            spectrum = create_fft_spectrum(
                channel=channel,
                time=self.data.time,
                name=f"Measure FFT({channel.name})",
                time_range=time_range,
                window_id="rectangular",
                remove_dc=True,
                zero_pad="next_pow2",
            )
        except Exception:
            return {"frequency": None, "period": None}
        if spectrum.frequency.size < 2:
            return {"frequency": None, "period": None}
        frequency = spectrum.frequency[1:]
        magnitude = spectrum.magnitude[1:]
        finite = np.isfinite(frequency) & np.isfinite(magnitude)
        if not np.any(finite):
            return {"frequency": None, "period": None}
        frequency = frequency[finite]
        magnitude = magnitude[finite]
        peak_frequency = float(frequency[int(np.argmax(magnitude))])
        if not np.isfinite(peak_frequency) or peak_frequency <= 0:
            return {"frequency": None, "period": None}
        return {"frequency": peak_frequency, "period": 1.0 / peak_frequency}

    def _set_measurements(self, measurements: dict[str, float | None]) -> None:
        units = {"period": " s", "frequency": " Hz"}
        for key, label in self.measure_labels.items():
            value = measurements.get(key)
            text = _format_value(value)
            if value is not None and np.isfinite(value) and key in units:
                text = f"{text}{units[key]}"
            label.setText(text)

    def _math_operand_changed(self) -> None:
        if not hasattr(self, "math_result_name"):
            return
        function_id = self.math_function.currentData()
        if function_id not in MATH_FUNCTION_BY_ID:
            return
        operand_a = self.math_operand_a.currentText()
        operand_b = self.math_operand_b.currentText() if MATH_FUNCTION_BY_ID[function_id].arity == 2 else None
        if operand_a:
            self.math_result_name.setText(default_result_name(function_id, operand_a, operand_b))

    def _start_operand_pick(self, operand: str, checked: bool) -> None:
        pick_id = f"math_{operand}"
        if not checked:
            if self.pending_waveform_pick == pick_id:
                self._clear_operand_pick()
            return
        self.pending_waveform_pick = pick_id
        self.pick_operand_a.setChecked(operand == "a")
        self.pick_operand_b.setChecked(operand == "b")
        if hasattr(self, "pick_measure_channel"):
            self.pick_measure_channel.setChecked(False)
        self.plot_tabs.setCurrentWidget(self.waveform_plot)
        self.statusBar().showMessage(self.tr("Click a waveform trace to select operand {operand}").format(operand=operand.upper()))

    def _start_measure_pick(self, checked: bool) -> None:
        if not checked:
            if self.pending_waveform_pick == "measure":
                self._clear_operand_pick()
            return
        self.pending_waveform_pick = "measure"
        self.pick_operand_a.setChecked(False)
        self.pick_operand_b.setChecked(False)
        self.pick_measure_channel.setChecked(True)
        self.plot_tabs.setCurrentWidget(self.waveform_plot)
        self.statusBar().showMessage(self.tr("Click a waveform trace to select the measurement waveform"))

    def _clear_operand_pick(self) -> None:
        self.pending_waveform_pick = None
        self.pick_operand_a.setChecked(False)
        self.pick_operand_b.setChecked(False)
        if hasattr(self, "pick_measure_channel"):
            self.pick_measure_channel.setChecked(False)

    def _waveform_picked(self, channel_name: str) -> None:
        if self.pending_waveform_pick is None:
            return
        if self.pending_waveform_pick == "measure":
            self.measure_channel.setCurrentText(channel_name)
            self._clear_operand_pick()
            self.statusBar().showMessage(self.tr("Measurement waveform: {name}").format(name=channel_name))
            return
        if self.pending_waveform_pick == "math_a":
            self.math_operand_a.setCurrentText(channel_name)
            operand = "A"
        else:
            self.math_operand_b.setCurrentText(channel_name)
            operand = "B"
        self._clear_operand_pick()
        self.statusBar().showMessage(self.tr("Operand {operand}: {name}").format(operand=operand, name=channel_name))

    def _add_math_output(self) -> None:
        if self.data is None:
            QtWidgets.QMessageBox.information(self, self.tr("Math"), self.tr("Load a CSV file before creating calculated traces."))
            return
        function_id = self.math_function.currentData()
        function = MATH_FUNCTION_BY_ID.get(function_id)
        if function is None:
            return
        try:
            if function.domain == "frequency":
                self._add_fft_spectrum()
            else:
                self._add_calculated_trace()
        except Exception as exc:  # noqa: BLE001 - user-facing calculation failure.
            QtWidgets.QMessageBox.warning(self, self.tr("Math failed"), str(exc))

    def _add_calculated_trace(self) -> None:
        if self.data is None:
            return
        name = self.math_result_name.text().strip()
        if not name:
            raise ValueError(self.tr("Calculated trace name cannot be empty"))
        if name in {channel.name for channel in self.data.channels}:
            raise ValueError(self.tr("A trace named {name!r} already exists").format(name=name))
        function_id = self.math_function.currentData()
        operand_a = self._channel_by_name(self.math_operand_a.currentText())
        operand_b = self._channel_by_name(self.math_operand_b.currentText()) if MATH_FUNCTION_BY_ID[function_id].arity == 2 else None
        if operand_a is None:
            raise ValueError(self.tr("Select operand A"))
        channel = create_calculated_channel(
            function_id=function_id,
            operand_a=operand_a,
            operand_b=operand_b,
            name=name,
            color=self._next_calculated_color(),
        )
        self.calculated_channels.append(channel)
        self._replace_active_data(select={channel.name})
        self._sync_math_outputs()
        self.statusBar().showMessage(self.tr("Added calculated trace: {name}").format(name=channel.name))

    def _add_fft_spectrum(self) -> None:
        if self.data is None:
            return
        name = self.math_result_name.text().strip()
        if not name:
            raise ValueError(self.tr("Spectrum name cannot be empty"))
        operand_a = self._channel_by_name(self.math_operand_a.currentText())
        if operand_a is None:
            raise ValueError(self.tr("Select operand A"))
        spectrum = create_fft_spectrum(
            channel=operand_a,
            time=self.data.time,
            name=name,
            time_range=self.waveform_plot.x_cursor_range(),
            window_id=self.fft_window.currentData(),
            remove_dc=self.fft_remove_dc.isChecked(),
            zero_pad=self.fft_zero_pad.currentData(),
        )
        self.spectra[name] = spectrum
        self.spectrum_plot.set_spectrum(spectrum)
        self._set_frequency_inputs(spectrum.frequency_range)
        self._sync_math_outputs()
        matching = self.math_outputs.findItems(name, QtCore.Qt.MatchFlag.MatchExactly)
        if matching:
            self.math_outputs.setCurrentItem(matching[0])
        self.statusBar().showMessage(
            self.tr("Updated spectrum: {name}, {window} window, {start:.8g} to {end:.8g}").format(
                name=name,
                window=spectrum.window_id,
                start=spectrum.time_range[0],
                end=spectrum.time_range[1],
            )
        )

    def _update_fft_spectrum(self) -> None:
        if self.data is None:
            return
        selected = self._selected_spectrum()
        if selected is None:
            self._add_math_output()
            return
        source_channel = self._channel_by_name(selected.source_channel)
        if source_channel is None:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Math failed"),
                self.tr("Source trace {name!r} is no longer available.").format(name=selected.source_channel),
            )
            return
        try:
            spectrum = create_fft_spectrum(
                channel=source_channel,
                time=self.data.time,
                name=selected.name,
                time_range=self.waveform_plot.x_cursor_range(),
                window_id=self.fft_window.currentData(),
                remove_dc=self.fft_remove_dc.isChecked(),
                zero_pad=self.fft_zero_pad.currentData(),
            )
        except Exception as exc:  # noqa: BLE001 - user-facing calculation failure.
            QtWidgets.QMessageBox.warning(self, self.tr("Math failed"), str(exc))
            return
        self.spectra[selected.name] = spectrum
        self.spectrum_plot.set_spectrum(spectrum)
        self._set_frequency_inputs(spectrum.frequency_range)
        self.statusBar().showMessage(
            self.tr("Updated spectrum: {name}, {window} window, {start:.8g} to {end:.8g}").format(
                name=spectrum.name,
                window=spectrum.window_id,
                start=spectrum.time_range[0],
                end=spectrum.time_range[1],
            )
        )

    def _remove_math_output(self) -> None:
        item = self.math_outputs.currentItem()
        if item is None:
            return
        name = item.text()
        original_channel_count = len(self.calculated_channels)
        self.calculated_channels = [channel for channel in self.calculated_channels if channel.name != name]
        removed_spectrum = self.spectra.pop(name, None)
        if len(self.calculated_channels) != original_channel_count:
            self._replace_active_data(select=set())
            self.statusBar().showMessage(self.tr("Removed calculated trace: {name}").format(name=name))
        if removed_spectrum is not None:
            self.spectrum_plot.clear()
            self.frequency_min.clear()
            self.frequency_max.clear()
            self.statusBar().showMessage(self.tr("Removed spectrum: {name}").format(name=name))
        self._sync_math_outputs()

    def _apply_frequency_range(self) -> None:
        spectrum = self._selected_spectrum()
        if spectrum is None:
            return
        low = _parse_float_text(self.frequency_min.text())
        high = _parse_float_text(self.frequency_max.text())
        if low is None or high is None:
            QtWidgets.QMessageBox.warning(self, self.tr("Spectrum Range"), self.tr("Enter numeric frequency bounds."))
            return
        self.spectrum_plot.set_frequency_range((low, high))
        self.spectra[spectrum.name] = SpectrumData(
            name=spectrum.name,
            frequency=spectrum.frequency,
            magnitude=spectrum.magnitude,
            source_channel=spectrum.source_channel,
            color=spectrum.color,
            time_range=spectrum.time_range,
            frequency_range=tuple(sorted((low, high))),
            window_id=spectrum.window_id,
            remove_dc=spectrum.remove_dc,
            zero_pad=spectrum.zero_pad,
            sample_count=spectrum.sample_count,
            fft_count=spectrum.fft_count,
        )

    def _math_output_selected(self, name: str) -> None:
        spectrum = self.spectra.get(name)
        if spectrum is not None:
            self.plot_tabs.setCurrentWidget(self.spectrum_plot)
            self.spectrum_plot.set_spectrum(spectrum)
            self._set_frequency_inputs(spectrum.frequency_range)
            function_index = self.math_function.findData("fft")
            if function_index >= 0:
                self.math_function.setCurrentIndex(function_index)
            self.math_operand_a.setCurrentText(spectrum.source_channel)
            self.fft_remove_dc.setChecked(spectrum.remove_dc)
            window_index = self.fft_window.findData(spectrum.window_id)
            if window_index >= 0:
                self.fft_window.setCurrentIndex(window_index)
            zero_pad_index = self.fft_zero_pad.findData(spectrum.zero_pad)
            if zero_pad_index >= 0:
                self.fft_zero_pad.setCurrentIndex(zero_pad_index)
            self.math_result_name.setText(spectrum.name)
            return
        if any(channel.name == name for channel in self.calculated_channels):
            self.plot_tabs.setCurrentWidget(self.waveform_plot)
            self.waveform_plot.focus_channel(name)
            self._sync_channel_checks()

    def _selected_spectrum(self) -> SpectrumData | None:
        item = self.math_outputs.currentItem()
        if item is None:
            return None
        return self.spectra.get(item.text())

    def _set_frequency_inputs(self, frequency_range: tuple[float, float]) -> None:
        self.frequency_min.setText(_format_value(frequency_range[0]))
        self.frequency_max.setText(_format_value(frequency_range[1]))

    def _replace_active_data(self, *, select: set[str]) -> None:
        if self.source_data is None:
            return
        self.data = WaveformData(
            time=self.source_data.time,
            channels=[*self.source_data.channels, *self.calculated_channels],
            ignored_columns=self.source_data.ignored_columns,
            source_path=self.source_data.source_path,
            time_column=self.source_data.time_column,
            sheet_name=self.source_data.sheet_name,
            time_candidates=self.source_data.time_candidates,
            timebase_kind=self.source_data.timebase_kind,
            timebase_value=self.source_data.timebase_value,
        )
        self.waveform_plot.replace_data_preserving_view(self.data, select=select)
        self._rebuild_channels(self.data.channels)
        self._rebuild_active_channel(self.data.channels)
        self._sync_math_controls()
        self._sync_measure_controls()
        self._update_cursor_panel()

    def _channel_by_name(self, name: str) -> ChannelData | None:
        if self.data is None:
            return None
        for channel in self.data.channels:
            if channel.name == name:
                return channel
        return None

    def _next_calculated_color(self) -> str:
        index = len(self.source_data.channels if self.source_data is not None else []) + len(self.calculated_channels)
        return OSCILLOSCOPE_COLORS[index % len(OSCILLOSCOPE_COLORS)]

    def _apply_timebase_settings(self, settings: TimebaseSettings) -> None:
        if self.source_data is None or self.data is None:
            return
        if (
            self.data.timebase_kind == settings.kind
            and self.data.time_column == settings.column
            and self.data.timebase_value == settings.value
        ):
            return
        self.calculated_channels.clear()
        self.spectra.clear()
        self.spectrum_plot.clear()
        self.frequency_min.clear()
        self.frequency_max.clear()
        self.source_data = _waveform_with_timebase(self.source_data, settings)
        self.data = self.source_data
        self.waveform_plot.set_data(self.data)
        self._rebuild_channels(self.data.channels)
        self._rebuild_active_channel(self.data.channels)
        self._sync_math_controls()
        self._sync_measure_controls()
        self._sync_math_outputs()
        self._sync_cursor_axis_selector()

    def _settings_for_current_channels(
        self,
        settings: dict[str, AxisGroupSettings],
    ) -> dict[str, AxisGroupSettings]:
        if self.data is None:
            return settings
        return {
            channel.name: settings.get(
                channel.name,
                AxisGroupSettings(_default_axis_group_for_channel(channel), channel.unit or ""),
            )
            for channel in self.data.channels
        }

    @staticmethod
    def _scroll_area(widget: QtWidgets.QWidget) -> QtWidgets.QScrollArea:
        area = QtWidgets.QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(widget)
        return area


def _toolbar_section_label(text: str) -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    label.setStyleSheet("QLabel { font-weight: 600; margin-left: 6px; margin-right: 2px; }")
    return label


def _toolbar_field_label(text: str) -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    label.setStyleSheet("QLabel { color: #666; margin-left: 4px; }")
    return label


def _format_value(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.8g}"


def _normalized_startup_language(language: str | None) -> str:
    if language is None or language.strip().lower() in {"", "system", "auto"}:
        return "system"
    return language.replace("-", "_")


def _default_axis_group_for_channel(channel: ChannelData) -> str:
    unit = (channel.unit or "").lower()
    if unit == "v":
        return "left"
    if unit == "a":
        return "right"
    return "disabled"


def _waveform_with_timebase(source: WaveformData, settings: TimebaseSettings) -> WaveformData:
    candidates = source.time_candidates or {
        channel.name: channel.values
        for channel in source.channels
    }
    sample_count = len(source.time)
    if candidates:
        sample_count = len(next(iter(candidates.values())))

    if settings.kind == "column":
        if settings.column is None or settings.column not in candidates:
            raise ValueError("Select a valid time column")
        time_values = candidates[settings.column].astype(float)
        time_column = settings.column
        timebase_value = None
    elif settings.kind == "sample_rate":
        if settings.value is None or settings.value <= 0:
            raise ValueError("Sample rate must be greater than zero")
        time_values = np.arange(sample_count, dtype=float) / settings.value
        time_column = None
        timebase_value = settings.value
    elif settings.kind == "time_step":
        if settings.value is None or settings.value <= 0:
            raise ValueError("Time step must be greater than zero")
        time_values = np.arange(sample_count, dtype=float) * settings.value
        time_column = None
        timebase_value = settings.value
    else:
        time_values = np.arange(sample_count, dtype=float)
        time_column = None
        timebase_value = None

    channel_names = [
        name for name in candidates
        if not (settings.kind == "column" and name == settings.column)
    ]
    channels = [
        ChannelData(
            name=name,
            values=candidates[name].astype(float),
            color=OSCILLOSCOPE_COLORS[index % len(OSCILLOSCOPE_COLORS)],
            unit=_guess_channel_unit(name),
        )
        for index, name in enumerate(channel_names)
    ]
    return WaveformData(
        time=time_values,
        channels=channels,
        ignored_columns=source.ignored_columns,
        source_path=source.source_path,
        time_column=time_column,
        sheet_name=source.sheet_name,
        time_candidates=candidates,
        timebase_kind=settings.kind,
        timebase_value=timebase_value,
    )


def _guess_channel_unit(name: str) -> str | None:
    lowered = name.lower()
    if lowered.startswith("v") or "voltage" in lowered:
        return "V"
    if lowered.startswith("i") or "current" in lowered:
        return "A"
    if lowered in {"r", "r_av"} or "resistance" in lowered:
        return "ohm"
    if lowered == "g" or "conductance" in lowered:
        return "S"
    return None


def _time_column_validation(values: np.ndarray | None) -> tuple[bool, str]:
    if values is None:
        return False, _viewer_tr("Select a time column.")
    if values.size < 2:
        return False, _viewer_tr("Time column needs at least two samples.")
    if not np.isfinite(values).all():
        return False, _viewer_tr("Time column contains non-finite values.")
    diffs = np.diff(values.astype(float))
    if not np.all(diffs > 0):
        return False, _viewer_tr("Time column must be strictly increasing.")
    spacing = float(np.median(diffs))
    tolerance = max(abs(spacing) * 1e-4, 1e-15)
    max_variation = float(np.max(np.abs(diffs - spacing)))
    if max_variation > tolerance:
        return (
            True,
            _viewer_tr("Increasing time column; nominal spacing: {spacing:.8g} s/pt (max step variation {variation:.3g}). FFT uses median spacing.").format(
                spacing=spacing,
                variation=max_variation,
            ),
        )
    return True, _viewer_tr("Uniform spacing: {spacing:.8g} s/pt.").format(spacing=spacing)


class WaveformSetupDialog(QtWidgets.QDialog):
    GROUP_COLUMN = 1
    UNIT_COLUMN = 2
    Y_MIN_COLUMN = 3
    Y_MAX_COLUMN = 4

    def __init__(
        self,
        data: WaveformData,
        current_settings: dict[str, AxisGroupSettings],
        group_defaults: dict[str, tuple[float, float]],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Waveform Setup"))
        self.resize(760, 560)
        self.data = data
        self.channels = data.channels
        self.time_candidates = data.time_candidates or {
            channel.name: channel.values
            for channel in data.channels
        }
        self.group_defaults = group_defaults

        time_box = QtWidgets.QGroupBox(self.tr("Time Base"))
        time_layout = QtWidgets.QGridLayout(time_box)
        time_layout.setContentsMargins(8, 8, 8, 8)
        self.timebase_mode = QtWidgets.QComboBox()
        self.timebase_mode.addItem(self.tr("Time column"), "column")
        self.timebase_mode.addItem(self.tr("Sample rate (Sa/s)"), "sample_rate")
        self.timebase_mode.addItem(self.tr("Sample interval (s/pt)"), "time_step")
        self.timebase_mode.addItem(self.tr("Sample index"), "sample_index")
        self.timebase_column = QtWidgets.QComboBox()
        self.timebase_column.addItems(list(self.time_candidates))
        self.timebase_value = QtWidgets.QLineEdit()
        self.timebase_status = QtWidgets.QLabel()
        self.timebase_status.setWordWrap(True)
        time_layout.addWidget(QtWidgets.QLabel(self.tr("Mode")), 0, 0)
        time_layout.addWidget(self.timebase_mode, 0, 1)
        time_layout.addWidget(QtWidgets.QLabel(self.tr("Column")), 1, 0)
        time_layout.addWidget(self.timebase_column, 1, 1)
        time_layout.addWidget(QtWidgets.QLabel(self.tr("Value")), 2, 0)
        time_layout.addWidget(self.timebase_value, 2, 1)
        time_layout.addWidget(self.timebase_status, 3, 0, 1, 2)
        time_layout.setColumnStretch(1, 1)

        self.table = QtWidgets.QTableWidget(len(self.channels), 5)
        self.table.setHorizontalHeaderLabels([self.tr("Waveform"), self.tr("Axis"), self.tr("Unit"), self.tr("Y min"), self.tr("Y max")])
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)

        for row, channel in enumerate(self.channels):
            settings = current_settings.get(channel.name, AxisGroupSettings("left", channel.unit or ""))
            name_item = QtWidgets.QTableWidgetItem(channel.name)
            name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, name_item)

            group_combo = QtWidgets.QComboBox()
            group_combo.addItem(self.tr("left"), "left")
            group_combo.addItem(self.tr("right"), "right")
            group_combo.addItem(self.tr("disabled"), "disabled")
            index = group_combo.findData(settings.group)
            if index >= 0:
                group_combo.setCurrentIndex(index)
            group_combo.currentTextChanged.connect(lambda _value, row=row: self._apply_default_range(row))
            self.table.setCellWidget(row, self.GROUP_COLUMN, group_combo)

            unit_item = QtWidgets.QTableWidgetItem(settings.unit or channel.unit or "")
            self.table.setItem(row, self.UNIT_COLUMN, unit_item)

            y_min, y_max = self._row_range(settings)
            self.table.setItem(row, self.Y_MIN_COLUMN, QtWidgets.QTableWidgetItem(_format_value(y_min)))
            self.table.setItem(row, self.Y_MAX_COLUMN, QtWidgets.QTableWidgetItem(_format_value(y_max)))

        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(time_box)
        layout.addWidget(self.table)
        layout.addWidget(self.buttons)

        self.timebase_mode.currentIndexChanged.connect(self._timebase_controls_changed)
        self.timebase_column.currentIndexChanged.connect(self._timebase_controls_changed)
        self.timebase_value.textChanged.connect(self._timebase_controls_changed)
        self._initialize_timebase_controls()

    def settings(self) -> dict[str, AxisGroupSettings]:
        result: dict[str, AxisGroupSettings] = {}
        for row, channel in enumerate(self.channels):
            group = self._group_at(row)
            unit_item = self.table.item(row, self.UNIT_COLUMN)
            y_min_item = self.table.item(row, self.Y_MIN_COLUMN)
            y_max_item = self.table.item(row, self.Y_MAX_COLUMN)
            result[channel.name] = AxisGroupSettings(
                group=group,
                unit=unit_item.text().strip() if unit_item is not None else "",
                y_min=_parse_float_item(y_min_item),
                y_max=_parse_float_item(y_max_item),
            )
        return result

    def timebase_settings(self) -> TimebaseSettings:
        kind = self.timebase_mode.currentData()
        if kind == "column":
            return TimebaseSettings(kind="column", column=self.timebase_column.currentText() or None)
        if kind in {"sample_rate", "time_step"}:
            return TimebaseSettings(kind=kind, value=_parse_float_text(self.timebase_value.text()))
        return TimebaseSettings(kind="sample_index")

    def _initialize_timebase_controls(self) -> None:
        mode_index = self.timebase_mode.findData(self.data.timebase_kind)
        if mode_index < 0:
            mode_index = self.timebase_mode.findData("column" if self.data.time_column else "sample_index")
        self.timebase_mode.setCurrentIndex(max(mode_index, 0))
        if self.data.time_column:
            self.timebase_column.setCurrentText(self.data.time_column)
        if self.data.timebase_value is not None:
            self.timebase_value.setText(_format_value(self.data.timebase_value))
        else:
            self.timebase_value.setText("1")
        self._timebase_controls_changed()

    def _timebase_controls_changed(self) -> None:
        kind = self.timebase_mode.currentData()
        self.timebase_column.setEnabled(kind == "column")
        self.timebase_value.setEnabled(kind in {"sample_rate", "time_step"})
        valid = True
        status = ""
        if kind == "column":
            values = self.time_candidates.get(self.timebase_column.currentText())
            valid, status = _time_column_validation(values)
        elif kind == "sample_rate":
            value = _parse_float_text(self.timebase_value.text())
            valid = value is not None and value > 0
            status = self.tr("Generated time from sample rate.") if valid else self.tr("Sample rate must be greater than zero.")
        elif kind == "time_step":
            value = _parse_float_text(self.timebase_value.text())
            valid = value is not None and value > 0
            status = self.tr("Generated time from sample interval.") if valid else self.tr("Sample interval must be greater than zero.")
        else:
            status = self.tr("Generated sample-index time base.")
        self.timebase_status.setText(status)
        ok_button = self.buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setEnabled(valid)

    def _apply_default_range(self, row: int) -> None:
        y_min, y_max = self.group_defaults.get(self._group_at(row), self._channel_range(row))
        if (y_min, y_max) == (0.0, 1.0):
            y_min, y_max = self._channel_range(row)
        self.table.setItem(row, self.Y_MIN_COLUMN, QtWidgets.QTableWidgetItem(_format_value(y_min)))
        self.table.setItem(row, self.Y_MAX_COLUMN, QtWidgets.QTableWidgetItem(_format_value(y_max)))

    def _row_range(self, settings: AxisGroupSettings) -> tuple[float, float]:
        if settings.y_min is not None and settings.y_max is not None:
            return settings.y_min, settings.y_max
        return self.group_defaults.get(settings.group, (0.0, 1.0))

    def _channel_range(self, row: int) -> tuple[float, float]:
        values = self.channels[row].values
        finite_values = values[np.isfinite(values)]
        if finite_values.size == 0:
            return 0.0, 1.0
        y_min = float(np.nanmin(finite_values))
        y_max = float(np.nanmax(finite_values))
        if y_min == y_max:
            y_max = y_min + 1.0
        return y_min, y_max

    def _group_at(self, row: int) -> str:
        widget = self.table.cellWidget(row, self.GROUP_COLUMN)
        if isinstance(widget, QtWidgets.QComboBox):
            return widget.currentData()
        return "left"


AxisSetupDialog = WaveformSetupDialog


def _parse_float_item(item: QtWidgets.QTableWidgetItem | None) -> float | None:
    if item is None:
        return None
    text = item.text().strip()
    return _parse_float_text(text)


def _parse_float_text(text: str) -> float | None:
    text = text.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None
