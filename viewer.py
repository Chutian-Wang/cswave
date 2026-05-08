from __future__ import annotations

from pathlib import Path

import numpy as np

from csv_loader import ChannelData, WaveformData, load_csv_waveform
from PySide6 import QtCore, QtGui, QtWidgets
from plot_widgets import AxisGroupSettings, WaveformPlot


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CSV Waveform Viewer")
        self.resize(1280, 820)
        self.data: WaveformData | None = None
        self.channel_checks: dict[str, QtWidgets.QCheckBox] = {}
        self.last_cursor_channel_by_group: dict[str, str] = {}

        self.waveform_plot = WaveformPlot()
        self.waveform_plot.cursorChanged.connect(self._update_cursor_panel)

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

        side_tabs = QtWidgets.QTabWidget()
        side_tabs.addTab(self._scroll_area(self.channel_panel), "Channels")
        side_tabs.addTab(cursor_panel, "Cursors")
        side_tabs.setMinimumWidth(260)

        splitter = QtWidgets.QSplitter()
        splitter.addWidget(self.waveform_plot)
        splitter.addWidget(side_tabs)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        self.setCentralWidget(splitter)

        self.statusBar().showMessage("Load a CSV file to begin")
        self._build_actions()
        self._build_shortcuts()

    def load_file(self, path: str | Path) -> None:
        data = load_csv_waveform(path)
        self.data = data
        self.waveform_plot.set_data(data)
        self._rebuild_channels(data.channels)
        self._rebuild_active_channel(data.channels)
        self._sync_cursor_axis_selector()
        ignored = f" Ignored {len(data.ignored_columns)} column(s)." if data.ignored_columns else ""
        time_source = data.time_column or "sample index"
        self.statusBar().showMessage(
            f"Loaded {data.source_path.name}: {len(data.channels)} channel(s), time base: {time_source}.{ignored}"
        )
        self._update_cursor_panel()

    def _build_actions(self) -> None:
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)

        open_action = QtGui.QAction("Open CSV", self)
        open_action.setShortcut(QtGui.QKeySequence.Open)
        open_action.triggered.connect(self._open_dialog)
        toolbar.addAction(open_action)

        reset_action = QtGui.QAction("Reset View", self)
        reset_action.triggered.connect(self.waveform_plot.reset_view)
        toolbar.addAction(reset_action)

        axis_setup_action = QtGui.QAction("Axis Groups", self)
        axis_setup_action.setToolTip("Configure left/right axis grouping, units, and Y ranges")
        axis_setup_action.triggered.connect(self._open_axis_setup)
        toolbar.addAction(axis_setup_action)

        toolbar.addSeparator()
        toolbar.addWidget(QtWidgets.QLabel("Zoom axis"))
        self.zoom_axis_selector = QtWidgets.QComboBox()
        self.zoom_axis_selector.addItems(["X", "Y"])
        self.zoom_axis_selector.setToolTip("Axis used by toolbar zoom buttons")
        toolbar.addWidget(self.zoom_axis_selector)

        zoom_in_action = QtGui.QAction("Zoom In", self)
        zoom_in_action.setToolTip("Zoom in on the selected axis")
        zoom_in_action.triggered.connect(lambda: self.waveform_plot.zoom_in(self._selected_zoom_axis()))
        toolbar.addAction(zoom_in_action)

        zoom_out_action = QtGui.QAction("Zoom Out", self)
        zoom_out_action.setToolTip("Zoom out on the selected axis")
        zoom_out_action.triggered.connect(lambda: self.waveform_plot.zoom_out(self._selected_zoom_axis()))
        toolbar.addAction(zoom_out_action)

    def _open_dialog(self) -> None:
        path, _selected_filter = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open CSV",
            str(Path.cwd()),
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        try:
            self.load_file(path)
        except Exception as exc:  # noqa: BLE001 - GUI needs user-facing failure.
            QtWidgets.QMessageBox.critical(self, "Could not load CSV", str(exc))

    def _selected_zoom_axis(self) -> str:
        return self.zoom_axis_selector.currentText().lower()

    def _build_shortcuts(self) -> None:
        toggle_axis = QtGui.QShortcut(QtGui.QKeySequence("T"), self)
        toggle_axis.activated.connect(self._toggle_axis_group)

    def _toggle_axis_group(self) -> None:
        self.waveform_plot.toggle_active_y_group()
        self.statusBar().showMessage(
            f"Y control group: {self.waveform_plot.active_y_group.capitalize()} axis"
        )

    def _open_axis_setup(self) -> None:
        if self.data is None:
            QtWidgets.QMessageBox.information(self, "Axis Groups", "Load a CSV file before configuring axes.")
            return
        dialog = AxisSetupDialog(self.data.channels, self.waveform_plot.axis_settings, self.waveform_plot.group_defaults(), self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        self.waveform_plot.update_axis_settings(dialog.settings())
        self._sync_channel_checks()
        self._rebuild_active_channel(self.data.channels)
        self._update_cursor_panel()

    def _build_cursor_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.x_cursor_toggle)
        layout.addWidget(self.y_cursor_toggle)
        reset_cursors = QtWidgets.QPushButton("Reset Cursors")
        reset_cursors.clicked.connect(self._reset_cursors)
        layout.addWidget(reset_cursors)
        layout.addWidget(QtWidgets.QLabel("Cursor axis group"))
        layout.addWidget(self.cursor_axis_selector)
        layout.addWidget(QtWidgets.QLabel("Active channel"))
        layout.addWidget(self.active_channel)

        grid = QtWidgets.QFormLayout()
        for name, label in self.cursor_labels.items():
            label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            grid.addRow(name, label)
        layout.addLayout(grid)
        layout.addStretch()
        return panel

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
            checkbox.setEnabled(self.waveform_plot.axis_settings[channel.name].group != "disabled")
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
            return "Disabled in Axis Groups"
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

    @staticmethod
    def _scroll_area(widget: QtWidgets.QWidget) -> QtWidgets.QScrollArea:
        area = QtWidgets.QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(widget)
        return area


def _format_value(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.8g}"


class AxisSetupDialog(QtWidgets.QDialog):
    GROUP_COLUMN = 1
    UNIT_COLUMN = 2
    Y_MIN_COLUMN = 3
    Y_MAX_COLUMN = 4

    def __init__(
        self,
        channels: list[ChannelData],
        current_settings: dict[str, AxisGroupSettings],
        group_defaults: dict[str, tuple[float, float]],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Axis Group Setup")
        self.resize(720, 420)
        self.channels = channels
        self.group_defaults = group_defaults

        self.table = QtWidgets.QTableWidget(len(channels), 5)
        self.table.setHorizontalHeaderLabels(["Waveform", "Axis", "Unit", "Y min", "Y max"])
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)

        for row, channel in enumerate(channels):
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

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addWidget(buttons)

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
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None
