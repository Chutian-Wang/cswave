from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from csv_loader import ChannelData, WaveformData


CURSOR_WIDTH = 2.25
ZERO_LINE_WIDTH = 1.4


class WaveformViewBox(pg.ViewBox):
    """Scope-like navigation: x-axis by default, y-axis with Control."""

    def wheelEvent(self, ev: QtGui.QWheelEvent) -> None:  # noqa: N802 - Qt override name.
        axis = "y" if _has_control_modifier(ev) else "x"
        delta = _wheel_delta(ev)
        if delta == 0:
            ev.ignore()
            return
        self.zoom_axis(axis, zoom_in=delta > 0, center=self._event_center(ev))
        ev.accept()

    def mouseDragEvent(self, ev: object, axis: int | None = None) -> None:  # noqa: N802 - Qt override name.
        ev.accept()
        current = self.mapToView(ev.pos())
        previous = self.mapToView(ev.lastPos())
        delta = previous - current
        if _has_control_modifier(ev):
            self.translateBy(y=delta.y())
        else:
            self.translateBy(x=delta.x())

    def zoom_axis(self, axis: str, *, zoom_in: bool, center: pg.Point | None = None) -> None:
        factor = 0.8 if zoom_in else 1.25
        if axis == "y":
            self.scaleBy(y=factor, center=center)
        else:
            self.scaleBy(x=factor, center=center)

    def _event_center(self, ev: QtGui.QWheelEvent) -> pg.Point | None:
        if hasattr(ev, "scenePosition"):
            scene_position = ev.scenePosition()
        elif hasattr(ev, "scenePos"):
            scene_position = ev.scenePos()
        else:
            scene_position = None
        if scene_position is None:
            return None
        return self.mapSceneToView(scene_position)


class WaveformPlot(QtWidgets.QWidget):
    cursorChanged = QtCore.Signal()
    viewRangeChanged = QtCore.Signal(tuple)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.data: WaveformData | None = None
        self.selected_channels: set[str] = set()
        self.curves: dict[str, pg.PlotDataItem] = {}
        self.preview_curves: dict[str, pg.PlotDataItem] = {}
        self._syncing_region = False
        self._syncing_view = False

        self.view_box = WaveformViewBox()
        self.plot = pg.PlotWidget(viewBox=self.view_box)
        self.plot.setBackground("#101214")
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.addLegend(offset=(8, 8))
        self.plot.setLabel("bottom", "Time")
        self.plot.setMouseEnabled(x=True, y=True)

        self.preview = pg.PlotWidget()
        self.preview.setBackground("#101214")
        self.preview.setMaximumHeight(120)
        self.preview.showGrid(x=True, y=False, alpha=0.15)
        self.preview.setMouseEnabled(x=False, y=False)
        self.preview.hideAxis("left")

        self.region = pg.LinearRegionItem()
        self.region.setZValue(20)
        self.preview.addItem(self.region)

        self.zero_line = pg.InfiniteLine(
            pos=0,
            angle=0,
            movable=False,
            pen=pg.mkPen("#f2f2f2", width=ZERO_LINE_WIDTH, style=QtCore.Qt.PenStyle.DashLine),
        )
        self.zero_line.setZValue(15)
        self.plot.addItem(self.zero_line, ignoreBounds=True)

        self.x_cursors = [
            pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen("#ffffff", width=CURSOR_WIDTH)),
            pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen("#aaaaaa", width=CURSOR_WIDTH)),
        ]
        self.y_cursors = [
            pg.InfiniteLine(angle=0, movable=True, pen=pg.mkPen("#ffffff", width=CURSOR_WIDTH)),
            pg.InfiniteLine(angle=0, movable=True, pen=pg.mkPen("#aaaaaa", width=CURSOR_WIDTH)),
        ]
        for line in self.x_cursors + self.y_cursors:
            line.setVisible(False)
            line.sigPositionChanged.connect(lambda *_args: self.cursorChanged.emit())
            self.plot.addItem(line, ignoreBounds=True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot, stretch=1)
        layout.addWidget(self.preview)

        self.plot.getViewBox().sigXRangeChanged.connect(self._on_x_range_changed)
        self.region.sigRegionChanged.connect(self._on_region_changed)

    def set_data(self, data: WaveformData) -> None:
        self.data = data
        self.selected_channels = {channel.name for channel in data.channels[: min(4, len(data.channels))]}
        self._redraw()
        self.reset_view()
        self._place_initial_cursors()

    def set_selected_channels(self, selected: set[str]) -> None:
        self.selected_channels = set(selected)
        self._redraw()

    def set_x_cursors_visible(self, visible: bool) -> None:
        for line in self.x_cursors:
            line.setVisible(visible)
        self.cursorChanged.emit()

    def set_y_cursors_visible(self, visible: bool) -> None:
        for line in self.y_cursors:
            line.setVisible(visible)
        self.cursorChanged.emit()

    def reset_view(self) -> None:
        if self.data is None or self.data.time.size == 0:
            return
        finite_time = self.data.time[np.isfinite(self.data.time)]
        if finite_time.size == 0:
            return
        x_min = float(np.nanmin(finite_time))
        x_max = float(np.nanmax(finite_time))
        if x_min == x_max:
            x_max = x_min + 1.0
        self.plot.setXRange(x_min, x_max, padding=0.0)
        self.plot.enableAutoRange(axis=pg.ViewBox.YAxis)
        self.region.setRegion((x_min, x_max))

    def zoom_in(self, axis: str) -> None:
        self.view_box.zoom_axis(axis, zoom_in=True)

    def zoom_out(self, axis: str) -> None:
        self.view_box.zoom_axis(axis, zoom_in=False)

    def cursor_values(self, active_channel_name: str | None = None) -> dict[str, float | None]:
        values: dict[str, float | None] = {
            "x1": self._line_value(self.x_cursors[0]),
            "x2": self._line_value(self.x_cursors[1]),
            "y1": self._line_value(self.y_cursors[0]),
            "y2": self._line_value(self.y_cursors[1]),
            "active_y1": None,
            "active_y2": None,
        }
        values["dx"] = _delta(values["x1"], values["x2"])
        values["dy"] = _delta(values["y1"], values["y2"])

        channel = self._channel_by_name(active_channel_name)
        if self.data is not None and channel is not None:
            values["active_y1"] = _interpolate(self.data.time, channel.values, values["x1"])
            values["active_y2"] = _interpolate(self.data.time, channel.values, values["x2"])
            values["active_dy"] = _delta(values["active_y1"], values["active_y2"])
        else:
            values["active_dy"] = None
        return values

    def _redraw(self) -> None:
        self.plot.clear()
        self.preview.clear()
        self.curves.clear()
        self.preview_curves.clear()
        self.plot.addItem(self.zero_line, ignoreBounds=True)
        self.preview.addItem(self.region)
        for line in self.x_cursors + self.y_cursors:
            self.plot.addItem(line, ignoreBounds=True)

        if self.data is None:
            return

        for channel in self.data.channels:
            if channel.name not in self.selected_channels:
                continue
            mask = np.isfinite(self.data.time) & np.isfinite(channel.values)
            pen = pg.mkPen(channel.color, width=1.6)
            preview_pen = pg.mkPen(channel.color, width=1.0)
            curve = self.plot.plot(
                self.data.time[mask],
                channel.values[mask],
                pen=pen,
                name=channel.name,
            )
            preview_curve = self.preview.plot(
                self.data.time[mask],
                channel.values[mask],
                pen=preview_pen,
            )
            self.curves[channel.name] = curve
            self.preview_curves[channel.name] = preview_curve

    def _place_initial_cursors(self) -> None:
        if self.data is None or self.data.time.size == 0:
            return
        finite_time = self.data.time[np.isfinite(self.data.time)]
        if finite_time.size == 0:
            return
        x_min = float(np.nanmin(finite_time))
        x_max = float(np.nanmax(finite_time))
        span = x_max - x_min or 1.0
        self.x_cursors[0].setValue(x_min + span * 0.33)
        self.x_cursors[1].setValue(x_min + span * 0.66)

        visible_values = []
        for channel in self.data.channels:
            if channel.name in self.selected_channels:
                visible_values.append(channel.values[np.isfinite(channel.values)])
        finite_values = np.concatenate(visible_values) if visible_values else np.array([])
        if finite_values.size:
            y_min = float(np.nanmin(finite_values))
            y_max = float(np.nanmax(finite_values))
            y_span = y_max - y_min or 1.0
            self.y_cursors[0].setValue(y_min + y_span * 0.33)
            self.y_cursors[1].setValue(y_min + y_span * 0.66)
        self.cursorChanged.emit()

    def _channel_by_name(self, name: str | None) -> ChannelData | None:
        if self.data is None or name is None:
            return None
        for channel in self.data.channels:
            if channel.name == name:
                return channel
        return None

    def _on_x_range_changed(self, _view_box: pg.ViewBox, ranges: tuple[float, float]) -> None:
        if self._syncing_view:
            return
        self._syncing_region = True
        self.region.setRegion(ranges)
        self._syncing_region = False
        self.viewRangeChanged.emit(tuple(float(value) for value in ranges))

    def _on_region_changed(self) -> None:
        if self._syncing_region:
            return
        low, high = self.region.getRegion()
        if low == high:
            return
        self._syncing_view = True
        self.plot.setXRange(low, high, padding=0.0)
        self._syncing_view = False

    @staticmethod
    def _line_value(line: pg.InfiniteLine) -> float | None:
        if not line.isVisible():
            return None
        return float(line.value())


def _delta(first: float | None, second: float | None) -> float | None:
    if first is None or second is None:
        return None
    return second - first


def _interpolate(time: np.ndarray, values: np.ndarray, x_value: float | None) -> float | None:
    if x_value is None:
        return None
    mask = np.isfinite(time) & np.isfinite(values)
    if mask.sum() < 2:
        return None
    x = time[mask]
    y = values[mask]
    order = np.argsort(x)
    x = x[order]
    y = y[order]
    if x_value < x[0] or x_value > x[-1]:
        return None
    return float(np.interp(x_value, x, y))


def _has_control_modifier(ev: object) -> bool:
    modifier_sources = []
    if hasattr(ev, "modifiers"):
        modifiers_method = ev.modifiers
        modifier_sources.append(modifiers_method() if callable(modifiers_method) else modifiers_method)
    modifier_sources.append(QtWidgets.QApplication.keyboardModifiers())
    if hasattr(QtWidgets.QApplication, "queryKeyboardModifiers"):
        modifier_sources.append(QtWidgets.QApplication.queryKeyboardModifiers())

    control_like_modifiers = (
        QtCore.Qt.KeyboardModifier.ControlModifier
        | QtCore.Qt.KeyboardModifier.MetaModifier
    )
    return any(bool(modifiers & control_like_modifiers) for modifiers in modifier_sources)


def _wheel_delta(ev: QtGui.QWheelEvent) -> int:
    if hasattr(ev, "angleDelta"):
        delta = ev.angleDelta().y()
        if delta:
            return delta
    if hasattr(ev, "delta"):
        return ev.delta()
    return 0
