from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from csv_loader import ChannelData, WaveformData

import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets


CURSOR_WIDTH = 2.25
ZERO_LINE_WIDTH = 1.4
PREVIEW_REGION_BOUNDARY_WIDTH = 1.5
PREVIEW_REGION_FRACTION = 0.30
CURVE_WIDTH = 1.6
PREVIEW_CURVE_WIDTH = 1.0
FOCUSED_CURVE_WIDTH = 3.0
FOCUSED_PREVIEW_CURVE_WIDTH = 1.8
DIMMED_CURVE_BLEND = 0.35
ZERO_LINE_Z = -100
CURVE_Z = 1
FOCUSED_CURVE_Z = 50
PLOT_BACKGROUND_COLOR = "#101214"
LEFT_AXIS_COLOR = "#ffd400"
RIGHT_AXIS_COLOR = "#00d7ff"


@dataclass
class AxisGroupSettings:
    group: str
    unit: str
    y_min: float | None = None
    y_max: float | None = None


class WaveformViewBox(pg.ViewBox):
    """Scope-like navigation: x-axis by default, y-axis with Control."""

    def __init__(self, y_target_getter: Callable[[], pg.ViewBox] | None = None) -> None:
        super().__init__()
        self.y_target_getter = y_target_getter

    def wheelEvent(self, ev: QtGui.QWheelEvent) -> None:  # noqa: N802 - Qt override name.
        axis = "y" if _has_control_modifier(ev) else "x"
        delta = _wheel_delta(ev)
        if delta == 0:
            ev.ignore()
            return
        self.zoom_axis(axis, zoom_in=delta > 0, center=self._event_center(ev, axis))
        ev.accept()

    def mouseDragEvent(self, ev: object, axis: int | None = None) -> None:  # noqa: N802 - Qt override name.
        ev.accept()
        current = self.mapToView(ev.pos())
        previous = self.mapToView(ev.lastPos())
        delta = previous - current
        if _has_control_modifier(ev):
            target = self._y_target()
            target_current = target.mapSceneToView(ev.scenePos())
            target_previous = target.mapSceneToView(ev.lastScenePos())
            target_delta = target_previous - target_current
            target.translateBy(y=target_delta.y())
        else:
            self.translateBy(x=delta.x())

    def zoom_axis(self, axis: str, *, zoom_in: bool, center: pg.Point | None = None) -> None:
        factor = 0.8 if zoom_in else 1.25
        if axis == "y":
            self._y_target().scaleBy(y=factor, center=center)
        else:
            self.scaleBy(x=factor, center=center)

    def _event_center(self, ev: QtGui.QWheelEvent, axis: str) -> pg.Point | None:
        if hasattr(ev, "scenePosition"):
            scene_position = ev.scenePosition()
        elif hasattr(ev, "scenePos"):
            scene_position = ev.scenePos()
        else:
            scene_position = None
        if scene_position is None:
            return None
        target = self._y_target() if axis == "y" else self
        return target.mapSceneToView(scene_position)

    def _y_target(self) -> pg.ViewBox:
        if self.y_target_getter is None:
            return self
        return self.y_target_getter()


class WaveformPlot(QtWidgets.QWidget):
    cursorChanged = QtCore.Signal()
    viewRangeChanged = QtCore.Signal(tuple)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.data: WaveformData | None = None
        self.selected_channels: set[str] = set()
        self.curves: dict[str, pg.PlotDataItem] = {}
        self.curve_groups: dict[str, str] = {}
        self.preview_curves: dict[str, pg.PlotDataItem] = {}
        self.preview_curve_groups: dict[str, str] = {}
        self.focused_channel: str | None = None
        self._syncing_region = False
        self._syncing_view = False
        self.active_y_group = "left"
        self.cursor_axis_group = "left"
        self._x_cursors_initialized = False
        self._y_cursors_initialized = False
        self.axis_settings: dict[str, AxisGroupSettings] = {}

        self.view_box = WaveformViewBox(self.active_y_view_box)
        self.plot = pg.PlotWidget(viewBox=self.view_box)
        self.plot_item = self.plot.getPlotItem()
        self.plot.setBackground(PLOT_BACKGROUND_COLOR)
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.legend = self.plot.addLegend(offset=(8, 8))
        self.plot.setLabel("bottom", "Time")
        self.plot.setMouseEnabled(x=True, y=True)
        self.plot_item.showAxis("right")

        self.right_view_box = pg.ViewBox()
        self.right_view_box.setXLink(self.view_box)
        self.right_view_box.setZValue(self.view_box.zValue() - 1)
        self.plot_item.scene().addItem(self.right_view_box)
        self.plot_item.getAxis("right").linkToView(self.right_view_box)
        self.plot_item.vb.sigResized.connect(self._update_right_view_geometry)

        self.preview = pg.PlotWidget()
        self.preview_item = self.preview.getPlotItem()
        self.preview.setBackground(PLOT_BACKGROUND_COLOR)
        self.preview.setMaximumHeight(120)
        self.preview.showGrid(x=True, y=False, alpha=0.15)
        self.preview.setMouseEnabled(x=False, y=False)
        self.preview_item.showAxis("right")
        self.preview_item.getAxis("left").setPen(pg.mkPen(LEFT_AXIS_COLOR, width=1))
        self.preview_item.getAxis("left").setTextPen(pg.mkPen(LEFT_AXIS_COLOR))
        self.preview_item.getAxis("right").setPen(pg.mkPen(RIGHT_AXIS_COLOR, width=1))
        self.preview_item.getAxis("right").setTextPen(pg.mkPen(RIGHT_AXIS_COLOR))

        self.preview_right_view_box = pg.ViewBox()
        self.preview_right_view_box.setXLink(self.preview_item.vb)
        self.preview_right_view_box.setZValue(self.preview_item.vb.zValue() - 1)
        self.preview_item.scene().addItem(self.preview_right_view_box)
        self.preview_item.getAxis("right").linkToView(self.preview_right_view_box)
        self.preview_item.vb.sigResized.connect(self._update_preview_right_view_geometry)

        self.region = pg.LinearRegionItem(
            pen=pg.mkPen((200, 200, 100), width=PREVIEW_REGION_BOUNDARY_WIDTH),
            hoverPen=pg.mkPen((255, 0, 0), width=PREVIEW_REGION_BOUNDARY_WIDTH),
        )
        self.region.setZValue(20)
        self.preview.addItem(self.region)

        self.zero_line = pg.InfiniteLine(
            pos=0,
            angle=0,
            movable=False,
            pen=pg.mkPen(LEFT_AXIS_COLOR, width=ZERO_LINE_WIDTH, style=QtCore.Qt.PenStyle.DashLine),
        )
        self.zero_line.setZValue(ZERO_LINE_Z)
        self.plot.addItem(self.zero_line, ignoreBounds=True)

        self.right_zero_line = pg.InfiniteLine(
            pos=0,
            angle=0,
            movable=False,
            pen=pg.mkPen(RIGHT_AXIS_COLOR, width=ZERO_LINE_WIDTH, style=QtCore.Qt.PenStyle.DashLine),
        )
        self.right_zero_line.setZValue(ZERO_LINE_Z)
        self.right_view_box.addItem(self.right_zero_line, ignoreBounds=True)

        self.preview_zero_line = pg.InfiniteLine(
            pos=0,
            angle=0,
            movable=False,
            pen=pg.mkPen(LEFT_AXIS_COLOR, width=1.0, style=QtCore.Qt.PenStyle.DashLine),
        )
        self.preview_right_zero_line = pg.InfiniteLine(
            pos=0,
            angle=0,
            movable=False,
            pen=pg.mkPen(RIGHT_AXIS_COLOR, width=1.0, style=QtCore.Qt.PenStyle.DashLine),
        )
        self.preview_zero_line.setZValue(ZERO_LINE_Z)
        self.preview_right_zero_line.setZValue(ZERO_LINE_Z)
        self.preview.addItem(self.preview_zero_line, ignoreBounds=True)
        self.preview_right_view_box.addItem(self.preview_right_zero_line, ignoreBounds=True)

        self.x_cursors = [
            pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen("#ffffff", width=CURSOR_WIDTH)),
            pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen("#aaaaaa", width=CURSOR_WIDTH)),
        ]
        self.y_cursors = [
            pg.InfiniteLine(angle=0, movable=True, pen=pg.mkPen("#ffffff", width=CURSOR_WIDTH)),
            pg.InfiniteLine(angle=0, movable=True, pen=pg.mkPen("#aaaaaa", width=CURSOR_WIDTH)),
        ]
        for line in self.x_cursors:
            line.setVisible(False)
            line.sigPositionChanged.connect(lambda *_args: self.cursorChanged.emit())
            self.plot.addItem(line, ignoreBounds=True)
        for line in self.y_cursors:
            line.setVisible(False)
            line.sigPositionChanged.connect(lambda *_args: self.cursorChanged.emit())
            self.view_box.addItem(line, ignoreBounds=True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot, stretch=1)
        layout.addWidget(self.preview)

        self.plot.getViewBox().sigXRangeChanged.connect(self._on_x_range_changed)
        self.plot.scene().sigMouseClicked.connect(self._on_plot_scene_clicked)
        self.region.sigRegionChangeFinished.connect(self._on_region_change_finished)
        self.update_axis_highlight()

    def set_data(self, data: WaveformData) -> None:
        self.data = data
        self.focused_channel = None
        self.axis_settings = {
            channel.name: AxisGroupSettings(group=_default_group_for_channel(channel), unit=channel.unit or "")
            for channel in data.channels
        }
        self.cursor_axis_group = self.active_y_group
        self._x_cursors_initialized = False
        self._y_cursors_initialized = False
        self._move_y_cursors_to_group(self.cursor_axis_group, preserve_visual_position=False)
        self.selected_channels = self.enabled_channel_names()
        self._redraw()
        self.reset_view()
        self.cursorChanged.emit()

    def set_selected_channels(self, selected: set[str]) -> None:
        self.selected_channels = set(selected)
        if self.focused_channel not in self.selected_channels:
            self.focused_channel = None
        self._redraw()

    def set_x_cursors_visible(self, visible: bool) -> None:
        if visible and not self._x_cursors_initialized:
            self._place_x_cursors_in_view()
            self._x_cursors_initialized = True
        for line in self.x_cursors:
            line.setVisible(visible)
        self._update_cursor_pens()
        self.cursorChanged.emit()

    def set_y_cursors_visible(self, visible: bool) -> None:
        if visible and not self._y_cursors_initialized:
            self.set_cursor_axis_group(self.active_y_group, preserve_visual_position=False)
            self._place_y_cursors_in_group(self.cursor_axis_group)
            self._y_cursors_initialized = True
        for line in self.y_cursors:
            line.setVisible(visible)
        self._update_cursor_pens()
        self.cursorChanged.emit()

    def reset_cursors_to_active_group_center(self) -> None:
        self.set_cursor_axis_group(self.active_y_group, preserve_visual_position=False)
        self._place_x_cursors_in_view()
        self._place_y_cursors_in_group(self.cursor_axis_group)
        self._x_cursors_initialized = True
        self._y_cursors_initialized = True
        self._update_cursor_pens()
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
        self.apply_axis_ranges(default_missing=True)
        self.region.setRegion((x_min, x_max))
        self._set_preview_range_for_region(x_min, x_max)

    def zoom_in(self, axis: str) -> None:
        self.view_box.zoom_axis(axis, zoom_in=True)

    def zoom_out(self, axis: str) -> None:
        self.view_box.zoom_axis(axis, zoom_in=False)

    def active_y_view_box(self) -> pg.ViewBox:
        return self.right_view_box if self.active_y_group == "right" else self.view_box

    def toggle_active_y_group(self) -> None:
        self.active_y_group = "right" if self.active_y_group == "left" else "left"
        self.update_axis_highlight()

    def set_active_y_group(self, group: str) -> None:
        self.active_y_group = "right" if group == "right" else "left"
        self.update_axis_highlight()

    def set_cursor_axis_group(self, group: str, *, preserve_visual_position: bool = True) -> None:
        group = "right" if group == "right" else "left"
        if group == self.cursor_axis_group:
            self._update_cursor_pens()
            self.cursorChanged.emit()
            return
        self._move_y_cursors_to_group(group, preserve_visual_position=preserve_visual_position)
        self.cursor_axis_group = group
        if not preserve_visual_position:
            self._place_y_cursors_in_group(group)
        self._update_cursor_pens()
        self.cursorChanged.emit()

    def channel_names_for_cursor_group(self) -> list[str]:
        if self.data is None:
            return []
        return [
            channel.name for channel in self.data.channels
            if self._channel_group(channel.name) == self.cursor_axis_group
            and channel.name in self.selected_channels
        ]

    def update_axis_settings(self, settings: dict[str, AxisGroupSettings]) -> None:
        changed_range_groups = self._groups_with_changed_membership(settings)
        previously_disabled = {
            name for name, setting in self.axis_settings.items()
            if setting.group == "disabled"
        }
        if changed_range_groups:
            settings = self._settings_with_recalculated_group_ranges(settings, changed_range_groups)
        self.axis_settings = settings
        newly_enabled = {
            name for name, setting in settings.items()
            if setting.group != "disabled" and name in previously_disabled
        }
        self.selected_channels.update(newly_enabled)
        if self.focused_channel is not None and self._channel_group(self.focused_channel) == "disabled":
            self.focused_channel = None
        self._redraw()
        self.apply_axis_ranges(default_missing=True)
        self.update_axis_highlight()

    def group_defaults(self) -> dict[str, tuple[float, float]]:
        return {
            group: self._default_group_range(group)
            for group in ("left", "right")
        }

    def enabled_channel_names(self) -> set[str]:
        return {
            channel.name for channel in self.data.channels
            if self._channel_group(channel.name) != "disabled"
        } if self.data is not None else set()

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
        self._clear_plot_curves()
        self._clear_preview_curves()
        self.curves.clear()
        self.curve_groups.clear()
        self.preview_curves.clear()
        self.preview_curve_groups.clear()

        if self.data is None:
            return

        for channel in self.data.channels:
            if channel.name not in self.selected_channels:
                continue
            group = self._channel_group(channel.name)
            if group == "disabled":
                continue
            mask = np.isfinite(self.data.time) & np.isfinite(channel.values)
            pen = pg.mkPen(channel.color, width=CURVE_WIDTH)
            preview_pen = pg.mkPen(channel.color, width=PREVIEW_CURVE_WIDTH)
            curve = pg.PlotDataItem(self.data.time[mask], channel.values[mask], pen=pen)
            curve.setZValue(CURVE_Z)
            curve.setCurveClickable(True, width=8)
            curve.sigClicked.connect(
                lambda _curve, event, name=channel.name: self._on_curve_clicked(name, event)
            )
            if group == "right":
                self.right_view_box.addItem(curve)
            else:
                self.plot_item.addItem(curve)
            _configure_curve_performance(curve)
            self.legend.addItem(curve, channel.name)
            preview_curve = pg.PlotDataItem(self.data.time[mask], channel.values[mask], pen=preview_pen)
            preview_curve.setZValue(CURVE_Z)
            if group == "right":
                self.preview_right_view_box.addItem(preview_curve)
            else:
                self.preview_item.addItem(preview_curve)
            _configure_curve_performance(preview_curve)
            self.curves[channel.name] = curve
            self.curve_groups[channel.name] = group
            self.preview_curves[channel.name] = preview_curve
            self.preview_curve_groups[channel.name] = group
        self._update_right_view_geometry()
        self._update_preview_right_view_geometry()
        self._update_curve_focus()

    def _clear_plot_curves(self) -> None:
        self.legend.clear()
        for name, curve in self.curves.items():
            if self.curve_groups.get(name) == "right":
                self.right_view_box.removeItem(curve)
            else:
                self.plot_item.removeItem(curve)

    def _clear_preview_curves(self) -> None:
        for name, curve in self.preview_curves.items():
            if self.preview_curve_groups.get(name) == "right":
                self.preview_right_view_box.removeItem(curve)
            else:
                self.preview_item.removeItem(curve)

    def _place_x_cursors_in_view(self) -> None:
        if self.data is None or self.data.time.size == 0:
            return
        x_min, x_max = self.view_box.viewRange()[0]
        span = x_max - x_min or 1.0
        self.x_cursors[0].setValue(x_min + span * 0.33)
        self.x_cursors[1].setValue(x_min + span * 0.66)

    def _place_y_cursors_in_group(self, group: str) -> None:
        y_min, y_max = self._current_group_view_range(group)
        y_span = y_max - y_min or 1.0
        self.y_cursors[0].setValue(y_min + y_span * 0.33)
        self.y_cursors[1].setValue(y_min + y_span * 0.66)

    def _current_group_view_range(self, group: str) -> tuple[float, float]:
        view_box = self._view_box_for_group(group)
        low, high = view_box.viewRange()[1]
        if low == high:
            high = low + 1.0
        return float(low), float(high)

    def _move_y_cursors_to_group(self, group: str, *, preserve_visual_position: bool) -> None:
        old_view_box = self._view_box_for_group(self.cursor_axis_group)
        new_view_box = self._view_box_for_group(group)
        new_values: list[float] = []
        if preserve_visual_position:
            for line in self.y_cursors:
                scene_position = old_view_box.mapViewToScene(pg.Point(0, line.value()))
                new_values.append(float(new_view_box.mapSceneToView(scene_position).y()))

        for view_box in (self.view_box, self.right_view_box):
            for line in self.y_cursors:
                if line in view_box.addedItems:
                    view_box.removeItem(line)
        for line in self.y_cursors:
            new_view_box.addItem(line, ignoreBounds=True)

        if preserve_visual_position:
            for line, value in zip(self.y_cursors, new_values, strict=True):
                line.setValue(value)

    def _view_box_for_group(self, group: str) -> pg.ViewBox:
        return self.right_view_box if group == "right" else self.view_box

    def _update_cursor_pens(self) -> None:
        highlighted = self.cursor_axis_group == self.active_y_group
        primary = "#ffffff" if highlighted else "#777777"
        secondary = "#aaaaaa" if highlighted else "#555555"
        for line in self.x_cursors[:1] + self.y_cursors[:1]:
            line.setPen(pg.mkPen(primary, width=CURSOR_WIDTH))
        for line in self.x_cursors[1:] + self.y_cursors[1:]:
            line.setPen(pg.mkPen(secondary, width=CURSOR_WIDTH))

    def _place_initial_cursors(self) -> None:
        self._place_x_cursors_in_view()
        self._place_y_cursors_in_group(self.cursor_axis_group)
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
        self._set_preview_range_for_region(ranges[0], ranges[1])
        self._syncing_region = False
        self.viewRangeChanged.emit(tuple(float(value) for value in ranges))

    def _on_curve_clicked(self, channel_name: str, event: object) -> None:
        if hasattr(event, "accept"):
            event.accept()
        self.focused_channel = channel_name
        self.set_active_y_group(self._channel_group(channel_name))
        self._update_curve_focus()

    def _on_plot_scene_clicked(self, event: object) -> None:
        button = event.button() if hasattr(event, "button") else None
        is_accepted = event.isAccepted() if hasattr(event, "isAccepted") else False
        if button != QtCore.Qt.MouseButton.LeftButton or is_accepted:
            return
        if self.focused_channel is None:
            return
        self.focused_channel = None
        self._update_curve_focus()

    def _on_region_change_finished(self) -> None:
        if self._syncing_region:
            return
        low, high = self.region.getRegion()
        if low == high:
            return
        self._syncing_view = True
        self.plot.setXRange(low, high, padding=0.0)
        self._set_preview_range_for_region(low, high)
        self._syncing_view = False

    def _set_preview_range_for_region(self, low: float, high: float) -> None:
        region_width = abs(high - low)
        if not np.isfinite(region_width) or region_width <= 0:
            return
        preview_width = region_width / PREVIEW_REGION_FRACTION
        center = (low + high) / 2.0
        preview_low = center - preview_width / 2.0
        preview_high = center + preview_width / 2.0
        self.preview.setXRange(preview_low, preview_high, padding=0.0)

    def _update_right_view_geometry(self) -> None:
        self.right_view_box.setGeometry(self.plot_item.vb.sceneBoundingRect())
        self.right_view_box.linkedViewChanged(self.plot_item.vb, self.right_view_box.XAxis)

    def _update_preview_right_view_geometry(self) -> None:
        self.preview_right_view_box.setGeometry(self.preview_item.vb.sceneBoundingRect())
        self.preview_right_view_box.linkedViewChanged(self.preview_item.vb, self.preview_right_view_box.XAxis)

    def apply_axis_ranges(self, *, default_missing: bool) -> None:
        for group, view_box, preview_view_box in (
            ("left", self.view_box, self.preview_item.vb),
            ("right", self.right_view_box, self.preview_right_view_box),
        ):
            y_min, y_max = self._configured_group_range(group)
            if (y_min is None or y_max is None) and default_missing:
                y_min, y_max = self._default_group_range(group)
            if y_min is None or y_max is None:
                continue
            if y_min == y_max:
                y_max = y_min + 1.0
            view_box.setYRange(float(y_min), float(y_max), padding=0.05)
            preview_view_box.setYRange(float(y_min), float(y_max), padding=0.05)
        self._update_axis_labels()

    def update_axis_highlight(self) -> None:
        left_color = LEFT_AXIS_COLOR if self.active_y_group == "left" else "#8a8f98"
        right_color = RIGHT_AXIS_COLOR if self.active_y_group == "right" else "#8a8f98"
        left_width = 2 if self.active_y_group == "left" else 1
        right_width = 2 if self.active_y_group == "right" else 1
        self.plot_item.getAxis("left").setPen(pg.mkPen(left_color, width=left_width))
        self.plot_item.getAxis("left").setTextPen(pg.mkPen(left_color))
        self.plot_item.getAxis("right").setPen(pg.mkPen(right_color, width=right_width))
        self.plot_item.getAxis("right").setTextPen(pg.mkPen(right_color))
        self.preview_item.getAxis("left").setPen(pg.mkPen(left_color, width=left_width))
        self.preview_item.getAxis("left").setTextPen(pg.mkPen(left_color))
        self.preview_item.getAxis("right").setPen(pg.mkPen(right_color, width=right_width))
        self.preview_item.getAxis("right").setTextPen(pg.mkPen(right_color))
        self._update_cursor_pens()
        self._update_axis_labels()

    def _update_curve_focus(self) -> None:
        for name, curve in self.curves.items():
            channel = self._channel_by_name(name)
            if channel is None:
                continue
            curve.setPen(self._curve_pen(channel, width=CURVE_WIDTH))
            curve.setZValue(self._curve_z_value(name))

        for name, curve in self.preview_curves.items():
            channel = self._channel_by_name(name)
            if channel is None:
                continue
            curve.setPen(self._curve_pen(channel, width=PREVIEW_CURVE_WIDTH, preview=True))
            curve.setZValue(self._curve_z_value(name))

        focused_group = self._channel_group(self.focused_channel) if self.focused_channel is not None else None
        self.right_view_box.setZValue(self.view_box.zValue() + 1 if focused_group == "right" else self.view_box.zValue() - 1)
        self.preview_right_view_box.setZValue(
            self.preview_item.vb.zValue() + 1 if focused_group == "right" else self.preview_item.vb.zValue() - 1
        )

    def _curve_pen(self, channel: ChannelData, *, width: float, preview: bool = False) -> QtGui.QPen:
        if self.focused_channel is None:
            return pg.mkPen(channel.color, width=width)
        if channel.name == self.focused_channel:
            focus_width = FOCUSED_PREVIEW_CURVE_WIDTH if preview else FOCUSED_CURVE_WIDTH
            return pg.mkPen(channel.color, width=focus_width)
        return pg.mkPen(_dimmed_curve_color(channel.color), width=width)

    def _curve_z_value(self, channel_name: str) -> int:
        return FOCUSED_CURVE_Z if channel_name == self.focused_channel else CURVE_Z

    def _update_axis_labels(self) -> None:
        left_unit = self._group_unit("left")
        right_unit = self._group_unit("right")
        self.plot_item.setLabel("left", f"Left axis{f' ({left_unit})' if left_unit else ''}")
        self.plot_item.setLabel("right", f"Right axis{f' ({right_unit})' if right_unit else ''}")
        self.preview_item.setLabel("left", left_unit)
        self.preview_item.setLabel("right", right_unit)

    def _configured_group_range(self, group: str) -> tuple[float | None, float | None]:
        endpoints = []
        for settings in self.axis_settings.values():
            if settings.group != group:
                continue
            if settings.y_min is not None:
                endpoints.append(settings.y_min)
            if settings.y_max is not None:
                endpoints.append(settings.y_max)
        if len(endpoints) < 2:
            return None, None
        return min(endpoints), max(endpoints)

    def _default_group_range(self, group: str) -> tuple[float, float]:
        if self.data is None:
            return 0.0, 1.0
        values = []
        for channel in self.data.channels:
            if self._channel_group(channel.name) == "disabled":
                continue
            if self._channel_group(channel.name) == group:
                finite_values = channel.values[np.isfinite(channel.values)]
                if finite_values.size:
                    values.append(finite_values)
        if not values:
            return 0.0, 1.0
        combined = np.concatenate(values)
        y_min = float(np.nanmin(combined))
        y_max = float(np.nanmax(combined))
        if y_min == y_max:
            y_max = y_min + 1.0
        return y_min, y_max

    def _groups_with_changed_membership(self, settings: dict[str, AxisGroupSettings]) -> set[str]:
        changed_groups: set[str] = set()
        for name, new_setting in settings.items():
            old_group = self._channel_group(name)
            new_group = _normalized_axis_group(new_setting.group)
            if old_group == new_group:
                continue
            if old_group in {"left", "right"}:
                changed_groups.add(old_group)
            if new_group in {"left", "right"}:
                changed_groups.add(new_group)
        return changed_groups

    def _settings_with_recalculated_group_ranges(
        self,
        settings: dict[str, AxisGroupSettings],
        groups: set[str],
    ) -> dict[str, AxisGroupSettings]:
        result = dict(settings)
        for group in groups:
            y_min, y_max = self._data_range_for_group(group, settings)
            for name, setting in list(result.items()):
                if _normalized_axis_group(setting.group) != group:
                    continue
                result[name] = AxisGroupSettings(
                    group=setting.group,
                    unit=setting.unit,
                    y_min=y_min,
                    y_max=y_max,
                )
        return result

    def _channel_group(self, channel_name: str) -> str:
        settings = self.axis_settings.get(channel_name)
        if settings is None:
            return "left"
        if settings.group == "disabled":
            return "disabled"
        return "right" if settings.group == "right" else "left"

    def _data_range_for_group(
        self,
        group: str,
        settings: dict[str, AxisGroupSettings] | None = None,
    ) -> tuple[float, float]:
        if self.data is None:
            return 0.0, 1.0
        values = []
        for channel in self.data.channels:
            if settings is None:
                channel_group = self._channel_group(channel.name)
            else:
                channel_setting = settings.get(channel.name)
                channel_group = _normalized_axis_group(channel_setting.group) if channel_setting is not None else "left"
            if channel_group != group:
                continue
            finite_values = channel.values[np.isfinite(channel.values)]
            if finite_values.size:
                values.append(finite_values)
        if not values:
            return 0.0, 1.0
        combined = np.concatenate(values)
        y_min = float(np.nanmin(combined))
        y_max = float(np.nanmax(combined))
        if y_min == y_max:
            y_max = y_min + 1.0
        return y_min, y_max

    def _group_unit(self, group: str) -> str:
        units = {
            settings.unit for settings in self.axis_settings.values()
            if settings.group == group and settings.unit
        }
        if len(units) == 1:
            return next(iter(units))
        if len(units) > 1:
            return "mixed"
        return ""

    @staticmethod
    def _line_value(line: pg.InfiniteLine) -> float | None:
        if not line.isVisible():
            return None
        return float(line.value())


def _delta(first: float | None, second: float | None) -> float | None:
    if first is None or second is None:
        return None
    return second - first


def _default_group_for_channel(channel: ChannelData) -> str:
    unit = (channel.unit or "").lower()
    if unit == "v":
        return "left"
    if unit == "a":
        return "right"
    return "disabled"


def _normalized_axis_group(group: str) -> str:
    if group == "disabled":
        return "disabled"
    return "right" if group == "right" else "left"


def _configure_curve_performance(curve: pg.PlotDataItem) -> None:
    curve.setClipToView(True)
    curve.setDownsampling(auto=True, method="peak")
    curve.setSkipFiniteCheck(True)


def _dimmed_curve_color(color: str) -> QtGui.QColor:
    source = QtGui.QColor(color)
    background = QtGui.QColor(PLOT_BACKGROUND_COLOR)
    dimmed = QtGui.QColor(
        round(background.red() + (source.red() - background.red()) * DIMMED_CURVE_BLEND),
        round(background.green() + (source.green() - background.green()) * DIMMED_CURVE_BLEND),
        round(background.blue() + (source.blue() - background.blue()) * DIMMED_CURVE_BLEND),
    )
    dimmed.setAlpha(255)
    return dimmed


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
