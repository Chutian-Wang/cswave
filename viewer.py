from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
from plot_widgets import AxisGroupSettings, SpectrumPlot, WaveformPlot


@dataclass(frozen=True)
class TimebaseSettings:
    kind: str
    column: str | None = None
    value: float | None = None


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("cswave")
        self.resize(1280, 820)
        self.data: WaveformData | None = None
        self.source_data: WaveformData | None = None
        self.calculated_channels: list[ChannelData] = []
        self.spectra: dict[str, SpectrumData] = {}
        self.channel_checks: dict[str, QtWidgets.QCheckBox] = {}
        self.last_cursor_channel_by_group: dict[str, str] = {}
        self.pending_math_operand_pick: str | None = None
        self._waveform_setup_pending = False

        self.waveform_plot = WaveformPlot()
        self.spectrum_plot = SpectrumPlot()
        self.waveform_plot.cursorChanged.connect(self._update_cursor_panel)
        self.waveform_plot.activeAxisGroupChanged.connect(self._sync_axis_group_selector)
        self.waveform_plot.traceClicked.connect(self._math_waveform_picked)

        self.channel_panel = QtWidgets.QWidget()
        self.channel_layout = QtWidgets.QVBoxLayout(self.channel_panel)
        self.channel_layout.setContentsMargins(8, 8, 8, 8)
        self.channel_layout.setSpacing(6)
        self.channel_layout.addWidget(QtWidgets.QLabel("Channels"))
        self.channel_layout.addStretch()

        self.active_channel = QtWidgets.QComboBox()
        self.cursor_axis_selector = QtWidgets.QComboBox()
        self.cursor_axis_selector.addItems(["left", "right"])
        self.cursor_axis_selector.currentTextChanged.connect(self._cursor_axis_changed)
        self.x_cursor_toggle = QtWidgets.QCheckBox("X cursors")
        self.y_cursor_toggle = QtWidgets.QCheckBox("Y cursors")
        self.x_cursor_toggle.toggled.connect(self._set_x_cursors_visible)
        self.y_cursor_toggle.toggled.connect(self._set_y_cursors_visible)
        self.active_channel.currentTextChanged.connect(self._active_channel_changed)

        self.cursor_labels = {
            key: QtWidgets.QLabel("-")
            for key in ("X1", "X2", "dX", "Y1", "Y2", "dY", "Active Y1", "Active Y2", "Active dY")
        }
        cursor_panel = self._build_cursor_panel()
        math_panel = self._build_math_panel()

        side_tabs = QtWidgets.QTabWidget()
        side_tabs.addTab(self._scroll_area(self.channel_panel), "Channels")
        side_tabs.addTab(cursor_panel, "Cursors")
        side_tabs.addTab(math_panel, "Math")
        side_tabs.setMinimumWidth(260)

        self.plot_tabs = QtWidgets.QTabWidget()
        self.plot_tabs.addTab(self.waveform_plot, "Waveforms")
        self.plot_tabs.addTab(self.spectrum_plot, "Spectrum")

        splitter = QtWidgets.QSplitter()
        splitter.addWidget(self.plot_tabs)
        splitter.addWidget(side_tabs)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        self.setCentralWidget(splitter)

        self.statusBar().showMessage("Load a waveform file to begin")
        self._build_actions()
        self._build_shortcuts()

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
        self._sync_math_outputs()
        self._sync_cursor_axis_selector()
        ignored = f" Ignored {len(data.ignored_columns)} column(s)." if data.ignored_columns else ""
        time_source = data.time_column or "sample index"
        sheet = f", sheet: {data.sheet_name}" if data.sheet_name else ""
        self.statusBar().showMessage(
            f"Loaded {data.source_path.name}{sheet}: {len(data.channels)} channel(s), time base: {time_source}.{ignored}"
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
        toolbar = self.addToolBar("Main")
        toolbar.setObjectName("MainToolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)

        toolbar.addWidget(_toolbar_section_label("File"))

        open_action = QtGui.QAction("Open Waveform", self)
        open_action.setShortcut(QtGui.QKeySequence.Open)
        open_action.triggered.connect(self._open_dialog)
        toolbar.addAction(open_action)

        toolbar.addSeparator()
        toolbar.addWidget(_toolbar_section_label("View"))

        reset_action = QtGui.QAction("Reset View", self)
        reset_action.triggered.connect(self._reset_active_view)
        toolbar.addAction(reset_action)

        waveform_setup_action = QtGui.QAction("Waveform Setup...", self)
        waveform_setup_action.setToolTip("Configure left/right axis grouping, units, and Y ranges")
        waveform_setup_action.triggered.connect(self._open_waveform_setup)
        toolbar.addAction(waveform_setup_action)

        toolbar.addSeparator()
        toolbar.addWidget(_toolbar_section_label("Navigate"))
        toolbar.addWidget(_toolbar_field_label("Y group"))
        self.axis_group_selector = QtWidgets.QComboBox()
        self.axis_group_selector.addItem("Left", "left")
        self.axis_group_selector.addItem("Right", "right")
        self.axis_group_selector.setToolTip("Active Y axis group for Y pan and zoom")
        self.axis_group_selector.setMinimumContentsLength(5)
        self._sync_axis_group_selector()
        self.axis_group_selector.currentIndexChanged.connect(self._axis_group_changed)
        toolbar.addWidget(self.axis_group_selector)

        toolbar.addWidget(_toolbar_field_label("Zoom"))
        self.zoom_axis_selector = QtWidgets.QComboBox()
        self.zoom_axis_selector.addItems(["X", "Y"])
        self.zoom_axis_selector.setToolTip("Axis used by toolbar zoom buttons")
        self.zoom_axis_selector.setMinimumContentsLength(1)
        toolbar.addWidget(self.zoom_axis_selector)

        zoom_in_action = QtGui.QAction("+", self)
        zoom_in_action.setToolTip("Zoom in on the selected axis")
        zoom_in_action.triggered.connect(lambda: self.waveform_plot.zoom_in(self._selected_zoom_axis()))
        toolbar.addAction(zoom_in_action)

        zoom_out_action = QtGui.QAction("-", self)
        zoom_out_action.setToolTip("Zoom out on the selected axis")
        zoom_out_action.triggered.connect(lambda: self.waveform_plot.zoom_out(self._selected_zoom_axis()))
        toolbar.addAction(zoom_out_action)

        toolbar.addSeparator()
        toolbar.addWidget(_toolbar_section_label("Display"))
        toolbar.addWidget(_toolbar_field_label("Renderer"))
        self.renderer_selector = QtWidgets.QComboBox()
        self.renderer_selector.addItem("CPU", "cpu")
        self.renderer_selector.addItem("OpenGL", "opengl")
        self.renderer_selector.setToolTip("Rendering backend for waveform drawing")
        self.renderer_selector.setMinimumContentsLength(6)
        self._sync_renderer_selector()
        self.renderer_selector.currentIndexChanged.connect(self._renderer_changed)
        toolbar.addWidget(self.renderer_selector)

    def _open_dialog(self) -> None:
        path, _selected_filter = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open Waveform",
            str(Path.cwd()),
            "Waveform files (*.csv *.xls *.xlsx *.xlsm);;CSV files (*.csv);;Excel files (*.xls *.xlsx *.xlsm);;All files (*)",
        )
        if not path:
            return
        try:
            self.load_file(path, show_setup=True)
        except Exception as exc:  # noqa: BLE001 - GUI needs user-facing failure.
            QtWidgets.QMessageBox.critical(self, "Could not load waveform", str(exc))

    def _select_excel_sheet(self, path: str | Path) -> str | None:
        sheets = excel_sheet_names(path)
        if not sheets:
            return None
        if len(sheets) == 1:
            return sheets[0]
        sheet, accepted = QtWidgets.QInputDialog.getItem(
            self,
            "Select Waveform Sheet",
            "Waveform sheet",
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
        self.statusBar().showMessage(f"Y control group: {self.waveform_plot.active_y_group.capitalize()} axis")

    def _sync_renderer_selector(self) -> None:
        opengl_index = self.renderer_selector.findData("opengl")
        if opengl_index >= 0:
            item = self.renderer_selector.model().item(opengl_index)
            if item is not None:
                item.setEnabled(self.waveform_plot.opengl_available)
            self.renderer_selector.setItemData(
                opengl_index,
                "Use OpenGL rendering" if self.waveform_plot.opengl_available else "OpenGL is not available",
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
            self.statusBar().showMessage(f"Renderer: {self.renderer_selector.currentText()}")
            self._sync_renderer_selector()
            return
        self._sync_renderer_selector()
        QtWidgets.QMessageBox.warning(self, "Renderer unavailable", "OpenGL rendering is not available on this system.")

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
        self.statusBar().showMessage(
            f"Y control group: {self.waveform_plot.active_y_group.capitalize()} axis"
        )

    def _toggle_x_cursors(self) -> None:
        self.x_cursor_toggle.setChecked(not self.x_cursor_toggle.isChecked())

    def _toggle_y_cursors(self) -> None:
        self.y_cursor_toggle.setChecked(not self.y_cursor_toggle.isChecked())

    def _open_waveform_setup(self) -> None:
        if self.data is None:
            QtWidgets.QMessageBox.information(self, "Waveform Setup", "Load a waveform file before configuring axes.")
            return
        dialog = AxisSetupDialog(self.data, self.waveform_plot.axis_settings, self.waveform_plot.group_defaults(), self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        self._apply_timebase_settings(dialog.timebase_settings())
        self.waveform_plot.update_axis_settings(self._settings_for_current_channels(dialog.settings()))
        self._sync_channel_checks()
        self._rebuild_active_channel(self.data.channels)
        self._update_cursor_panel()

    def _open_axis_setup(self) -> None:
        self._open_waveform_setup()

    def _build_cursor_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        controls = QtWidgets.QGroupBox("Controls")
        controls_layout = QtWidgets.QGridLayout(controls)
        controls_layout.setContentsMargins(8, 8, 8, 8)
        controls_layout.addWidget(self.x_cursor_toggle, 0, 0)
        controls_layout.addWidget(self.y_cursor_toggle, 0, 1)
        reset_cursors = QtWidgets.QPushButton("Reset Cursors")
        reset_cursors.clicked.connect(self._reset_cursors)
        controls_layout.addWidget(reset_cursors, 1, 0, 1, 2)
        controls_layout.addWidget(QtWidgets.QLabel("Cursor group"), 2, 0)
        controls_layout.addWidget(self.cursor_axis_selector, 2, 1)
        controls_layout.addWidget(QtWidgets.QLabel("Active channel"), 3, 0)
        controls_layout.addWidget(self.active_channel, 3, 1)
        controls_layout.setColumnStretch(1, 1)
        layout.addWidget(controls)

        layout.addWidget(self._cursor_group_box("X Positions", [("X1", "X1"), ("X2", "X2"), ("Delta X", "dX")]))
        layout.addWidget(self._cursor_group_box("Y Positions", [("Y1", "Y1"), ("Y2", "Y2"), ("Delta Y", "dY")]))
        layout.addWidget(
            self._cursor_group_box(
                "Active Channel",
                [("Y at X1", "Active Y1"), ("Y at X2", "Active Y2"), ("Delta", "Active dY")],
            )
        )
        layout.addStretch()
        return panel

    def _cursor_group_box(self, title: str, rows: list[tuple[str, str]]) -> QtWidgets.QGroupBox:
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

    def _build_math_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        builder = QtWidgets.QGroupBox("Builder")
        form = QtWidgets.QFormLayout(builder)
        form.setContentsMargins(8, 8, 8, 8)

        self.math_function = QtWidgets.QComboBox()
        for function in MATH_FUNCTIONS:
            self.math_function.addItem(function.label, function.id)
        self.math_function.currentIndexChanged.connect(self._math_function_changed)
        form.addRow("Function", self.math_function)

        self.math_operand_a = QtWidgets.QComboBox()
        self.math_operand_a.currentIndexChanged.connect(self._math_operand_changed)
        self.pick_operand_a = QtWidgets.QPushButton("Pick")
        self.pick_operand_a.setCheckable(True)
        self.pick_operand_a.setToolTip("Click, then click a waveform trace to use it as operand A")
        self.pick_operand_a.clicked.connect(lambda checked: self._start_operand_pick("a", checked))
        form.addRow("A", self._operand_picker_row(self.math_operand_a, self.pick_operand_a))

        self.math_operand_b = QtWidgets.QComboBox()
        self.math_operand_b.currentIndexChanged.connect(self._math_operand_changed)
        self.math_operand_b_label = QtWidgets.QLabel("B")
        self.pick_operand_b = QtWidgets.QPushButton("Pick")
        self.pick_operand_b.setCheckable(True)
        self.pick_operand_b.setToolTip("Click, then click a waveform trace to use it as operand B")
        self.pick_operand_b.clicked.connect(lambda checked: self._start_operand_pick("b", checked))
        self.math_operand_b_row = self._operand_picker_row(self.math_operand_b, self.pick_operand_b)
        form.addRow(self.math_operand_b_label, self.math_operand_b_row)

        self.fft_window = QtWidgets.QComboBox()
        for window in WINDOW_FUNCTIONS:
            self.fft_window.addItem(window.label, window.id)
        self.fft_window_label = QtWidgets.QLabel("Window")
        form.addRow(self.fft_window_label, self.fft_window)

        self.fft_remove_dc = QtWidgets.QCheckBox("Remove DC offset")
        form.addRow(self.fft_remove_dc)

        self.fft_zero_pad = QtWidgets.QComboBox()
        for option_id, label in ZERO_PAD_OPTIONS:
            self.fft_zero_pad.addItem(label, option_id)
        self.fft_zero_pad.setToolTip(
            "Adds zeros after the selected waveform segment to create denser FFT bins. "
            "Does not improve true frequency resolution."
        )
        self.fft_zero_pad_label = QtWidgets.QLabel("Zero pad")
        form.addRow(self.fft_zero_pad_label, self.fft_zero_pad)

        self.math_result_name = QtWidgets.QLineEdit()
        form.addRow("Name", self.math_result_name)

        buttons = QtWidgets.QWidget()
        buttons_layout = QtWidgets.QHBoxLayout(buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        add_button = QtWidgets.QPushButton("Add")
        add_button.clicked.connect(self._add_math_output)
        self.update_fft_button = QtWidgets.QPushButton("Update FFT")
        self.update_fft_button.clicked.connect(self._update_fft_spectrum)
        buttons_layout.addWidget(add_button)
        buttons_layout.addWidget(self.update_fft_button)
        form.addRow(buttons)
        layout.addWidget(builder)

        spectrum = QtWidgets.QGroupBox("Spectrum Range")
        spectrum_form = QtWidgets.QFormLayout(spectrum)
        spectrum_form.setContentsMargins(8, 8, 8, 8)
        self.frequency_min = QtWidgets.QLineEdit()
        self.frequency_max = QtWidgets.QLineEdit()
        apply_frequency = QtWidgets.QPushButton("Apply Frequency Range")
        apply_frequency.clicked.connect(self._apply_frequency_range)
        spectrum_form.addRow("Min Hz", self.frequency_min)
        spectrum_form.addRow("Max Hz", self.frequency_max)
        spectrum_form.addRow(apply_frequency)
        layout.addWidget(spectrum)

        outputs = QtWidgets.QGroupBox("Outputs")
        outputs_layout = QtWidgets.QVBoxLayout(outputs)
        outputs_layout.setContentsMargins(8, 8, 8, 8)
        self.math_outputs = QtWidgets.QListWidget()
        self.math_outputs.currentTextChanged.connect(self._math_output_selected)
        self.math_outputs.itemClicked.connect(lambda item: self._math_output_selected(item.text()))
        remove_button = QtWidgets.QPushButton("Remove")
        remove_button.clicked.connect(self._remove_math_output)
        outputs_layout.addWidget(self.math_outputs)
        outputs_layout.addWidget(remove_button)
        layout.addWidget(outputs)
        layout.addStretch()

        self._math_function_changed()
        return panel

    @staticmethod
    def _operand_picker_row(combo: QtWidgets.QComboBox, button: QtWidgets.QPushButton) -> QtWidgets.QWidget:
        row = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(combo, stretch=1)
        layout.addWidget(button)
        return row

    def _rebuild_channels(self, channels: list[ChannelData]) -> None:
        while self.channel_layout.count() > 2:
            item = self.channel_layout.takeAt(1)
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
            return "Disabled in Waveform Setup"
        return "Show or hide this enabled waveform"

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
        self.cursor_axis_selector.setCurrentText(self.waveform_plot.cursor_axis_group)
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
        if not is_binary and self.pending_math_operand_pick == "b":
            self._clear_operand_pick()
        self.fft_window.setEnabled(is_fft)
        self.fft_window.setVisible(is_fft)
        self.fft_window_label.setVisible(is_fft)
        self.fft_remove_dc.setVisible(is_fft)
        self.fft_zero_pad.setVisible(is_fft)
        self.fft_zero_pad_label.setVisible(is_fft)
        self.update_fft_button.setVisible(is_fft)
        self._math_operand_changed()

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
        if not checked:
            if self.pending_math_operand_pick == operand:
                self._clear_operand_pick()
            return
        self.pending_math_operand_pick = operand
        self.pick_operand_a.setChecked(operand == "a")
        self.pick_operand_b.setChecked(operand == "b")
        self.plot_tabs.setCurrentWidget(self.waveform_plot)
        self.statusBar().showMessage(f"Click a waveform trace to select operand {operand.upper()}")

    def _clear_operand_pick(self) -> None:
        self.pending_math_operand_pick = None
        self.pick_operand_a.setChecked(False)
        self.pick_operand_b.setChecked(False)

    def _math_waveform_picked(self, channel_name: str) -> None:
        if self.pending_math_operand_pick is None:
            return
        if self.pending_math_operand_pick == "a":
            self.math_operand_a.setCurrentText(channel_name)
            operand = "A"
        else:
            self.math_operand_b.setCurrentText(channel_name)
            operand = "B"
        self._clear_operand_pick()
        self.statusBar().showMessage(f"Operand {operand}: {channel_name}")

    def _add_math_output(self) -> None:
        if self.data is None:
            QtWidgets.QMessageBox.information(self, "Math", "Load a CSV file before creating calculated traces.")
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
            QtWidgets.QMessageBox.warning(self, "Math failed", str(exc))

    def _add_calculated_trace(self) -> None:
        if self.data is None:
            return
        name = self.math_result_name.text().strip()
        if not name:
            raise ValueError("Calculated trace name cannot be empty")
        if name in {channel.name for channel in self.data.channels}:
            raise ValueError(f"A trace named {name!r} already exists")
        function_id = self.math_function.currentData()
        operand_a = self._channel_by_name(self.math_operand_a.currentText())
        operand_b = self._channel_by_name(self.math_operand_b.currentText()) if MATH_FUNCTION_BY_ID[function_id].arity == 2 else None
        if operand_a is None:
            raise ValueError("Select operand A")
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
        self.statusBar().showMessage(f"Added calculated trace: {channel.name}")

    def _add_fft_spectrum(self) -> None:
        if self.data is None:
            return
        name = self.math_result_name.text().strip()
        if not name:
            raise ValueError("Spectrum name cannot be empty")
        operand_a = self._channel_by_name(self.math_operand_a.currentText())
        if operand_a is None:
            raise ValueError("Select operand A")
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
            f"Updated spectrum: {name}, {spectrum.window_id} window, {spectrum.time_range[0]:.8g} to {spectrum.time_range[1]:.8g}"
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
                "Math failed",
                f"Source trace {selected.source_channel!r} is no longer available.",
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
            QtWidgets.QMessageBox.warning(self, "Math failed", str(exc))
            return
        self.spectra[selected.name] = spectrum
        self.spectrum_plot.set_spectrum(spectrum)
        self._set_frequency_inputs(spectrum.frequency_range)
        self.statusBar().showMessage(
            f"Updated spectrum: {spectrum.name}, {spectrum.window_id} window, {spectrum.time_range[0]:.8g} to {spectrum.time_range[1]:.8g}"
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
            self.statusBar().showMessage(f"Removed calculated trace: {name}")
        if removed_spectrum is not None:
            self.spectrum_plot.clear()
            self.frequency_min.clear()
            self.frequency_max.clear()
            self.statusBar().showMessage(f"Removed spectrum: {name}")
        self._sync_math_outputs()

    def _apply_frequency_range(self) -> None:
        spectrum = self._selected_spectrum()
        if spectrum is None:
            return
        low = _parse_float_text(self.frequency_min.text())
        high = _parse_float_text(self.frequency_max.text())
        if low is None or high is None:
            QtWidgets.QMessageBox.warning(self, "Spectrum Range", "Enter numeric frequency bounds.")
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
        return False, "Select a time column."
    if values.size < 2:
        return False, "Time column needs at least two samples."
    if not np.isfinite(values).all():
        return False, "Time column contains non-finite values."
    diffs = np.diff(values.astype(float))
    if not np.all(diffs > 0):
        return False, "Time column must be strictly increasing."
    spacing = float(np.median(diffs))
    tolerance = max(abs(spacing) * 1e-4, 1e-15)
    max_variation = float(np.max(np.abs(diffs - spacing)))
    if max_variation > tolerance:
        return (
            True,
            f"Increasing time column; nominal spacing: {spacing:.8g} s/pt "
            f"(max step variation {max_variation:.3g}). FFT uses median spacing.",
        )
    return True, f"Uniform spacing: {spacing:.8g} s/pt."


class AxisSetupDialog(QtWidgets.QDialog):
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
        self.setWindowTitle("Waveform Setup")
        self.resize(760, 560)
        self.data = data
        self.channels = data.channels
        self.time_candidates = data.time_candidates or {
            channel.name: channel.values
            for channel in data.channels
        }
        self.group_defaults = group_defaults

        time_box = QtWidgets.QGroupBox("Time Base")
        time_layout = QtWidgets.QGridLayout(time_box)
        time_layout.setContentsMargins(8, 8, 8, 8)
        self.timebase_mode = QtWidgets.QComboBox()
        self.timebase_mode.addItem("Time column", "column")
        self.timebase_mode.addItem("Sample rate (Sa/s)", "sample_rate")
        self.timebase_mode.addItem("Sample interval (s/pt)", "time_step")
        self.timebase_mode.addItem("Sample index", "sample_index")
        self.timebase_column = QtWidgets.QComboBox()
        self.timebase_column.addItems(list(self.time_candidates))
        self.timebase_value = QtWidgets.QLineEdit()
        self.timebase_status = QtWidgets.QLabel()
        self.timebase_status.setWordWrap(True)
        time_layout.addWidget(QtWidgets.QLabel("Mode"), 0, 0)
        time_layout.addWidget(self.timebase_mode, 0, 1)
        time_layout.addWidget(QtWidgets.QLabel("Column"), 1, 0)
        time_layout.addWidget(self.timebase_column, 1, 1)
        time_layout.addWidget(QtWidgets.QLabel("Value"), 2, 0)
        time_layout.addWidget(self.timebase_value, 2, 1)
        time_layout.addWidget(self.timebase_status, 3, 0, 1, 2)
        time_layout.setColumnStretch(1, 1)

        self.table = QtWidgets.QTableWidget(len(self.channels), 5)
        self.table.setHorizontalHeaderLabels(["Waveform", "Axis", "Unit", "Y min", "Y max"])
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
            group_combo.addItems(["left", "right", "disabled"])
            group_combo.setCurrentText(settings.group)
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
            status = "Generated time from sample rate." if valid else "Sample rate must be greater than zero."
        elif kind == "time_step":
            value = _parse_float_text(self.timebase_value.text())
            valid = value is not None and value > 0
            status = "Generated time from sample interval." if valid else "Sample interval must be greater than zero."
        else:
            status = "Generated sample-index time base."
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
            return widget.currentText()
        return "left"


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
