from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from csv_loader import ChannelData, WaveformData, load_csv_waveform
from plot_widgets import WaveformPlot


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CSV Waveform Viewer")
        self.resize(1280, 820)
        self.data: WaveformData | None = None
        self.channel_checks: dict[str, QtWidgets.QCheckBox] = {}

        self.waveform_plot = WaveformPlot()
        self.waveform_plot.cursorChanged.connect(self._update_cursor_panel)

        self.channel_panel = QtWidgets.QWidget()
        self.channel_layout = QtWidgets.QVBoxLayout(self.channel_panel)
        self.channel_layout.setContentsMargins(8, 8, 8, 8)
        self.channel_layout.setSpacing(6)
        self.channel_layout.addWidget(QtWidgets.QLabel("Channels"))
        self.channel_layout.addStretch()

        self.active_channel = QtWidgets.QComboBox()
        self.x_cursor_toggle = QtWidgets.QCheckBox("X cursors")
        self.y_cursor_toggle = QtWidgets.QCheckBox("Y cursors")
        self.x_cursor_toggle.toggled.connect(self.waveform_plot.set_x_cursors_visible)
        self.y_cursor_toggle.toggled.connect(self.waveform_plot.set_y_cursors_visible)
        self.active_channel.currentTextChanged.connect(self._update_cursor_panel)

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

    def load_file(self, path: str | Path) -> None:
        data = load_csv_waveform(path)
        self.data = data
        self.waveform_plot.set_data(data)
        self._rebuild_channels(data.channels)
        self._rebuild_active_channel(data.channels)
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

    def _build_cursor_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.x_cursor_toggle)
        layout.addWidget(self.y_cursor_toggle)
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
            checkbox.toggled.connect(self._channel_selection_changed)
            checkbox.setStyleSheet(f"QCheckBox {{ color: {channel.color}; }}")
            self.channel_checks[channel.name] = checkbox
            self.channel_layout.insertWidget(self.channel_layout.count() - 1, checkbox)

    def _rebuild_active_channel(self, channels: list[ChannelData]) -> None:
        self.active_channel.blockSignals(True)
        self.active_channel.clear()
        self.active_channel.addItems([channel.name for channel in channels])
        self.active_channel.blockSignals(False)

    def _channel_selection_changed(self) -> None:
        selected = {
            name
            for name, checkbox in self.channel_checks.items()
            if checkbox.isChecked()
        }
        self.waveform_plot.set_selected_channels(selected)
        self._update_cursor_panel()

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
