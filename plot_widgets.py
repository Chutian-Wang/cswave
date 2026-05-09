from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import os
import sys

import numpy as np

from csv_loader import ChannelData, WaveformData
from math_engine import SpectrumData, filtered_spectrum

import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets


CURSOR_WIDTH = 2.25
CURSOR_LABEL_FILL = (16, 18, 20, 210)
CURSOR_LABEL_BORDER = (220, 220, 220, 120)
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
MAIN_DOWNSAMPLE_METHOD = "peak"
INTERACTION_DOWNSAMPLE_METHOD = "subsample"
PREVIEW_DOWNSAMPLE_METHOD = "subsample"
INTERACTION_SETTLE_MS = 140
PREVIEW_RANGE_UPDATE_MS = 45
PREVIEW_WHEEL_ZOOM_IN_FACTOR = 0.8
PREVIEW_WHEEL_ZOOM_OUT_FACTOR = 1.25
OPENGL_ENV_VAR = "CSWAVE_OPENGL"
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

    interactionStarted = QtCore.Signal()

    def __init__(
        self,
        y_target_getter: Callable[[], pg.ViewBox] | None = None,
        *,
        x_target_getter: Callable[[], pg.ViewBox] | None = None,
        free_pan_getter: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__()
        self.y_target_getter = y_target_getter
        self.x_target_getter = x_target_getter
        self.free_pan_getter = free_pan_getter

    def wheelEvent(self, ev: QtGui.QWheelEvent, axis: int | None = None) -> None:  # noqa: N802 - Qt override name.
        zoom_axis = _wheel_axis_from_event(ev, axis)
        delta = _wheel_delta(ev)
        if delta == 0:
            ev.ignore()
            return
        self.zoom_axis(zoom_axis, zoom_in=delta > 0, center=self._event_center(ev, zoom_axis))
        ev.accept()

    def mouseDragEvent(self, ev: object, axis: int | None = None) -> None:  # noqa: N802 - Qt override name.
        ev.accept()
        self.interactionStarted.emit()
        if self._free_pan_enabled():
            self._free_pan(ev)
            return
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
        self.interactionStarted.emit()
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

    def _x_target(self) -> pg.ViewBox:
        if self.x_target_getter is None:
            return self
        return self.x_target_getter()

    def _free_pan_enabled(self) -> bool:
        return self.free_pan_getter() if self.free_pan_getter is not None else False

    def _free_pan(self, ev: object) -> None:
        x_target = self._x_target()
        y_target = self._y_target()
        scene_position = ev.scenePos()
        last_scene_position = ev.lastScenePos()
        current_x = x_target.mapSceneToView(scene_position)
        previous_x = x_target.mapSceneToView(last_scene_position)
        current_y = y_target.mapSceneToView(scene_position)
        previous_y = y_target.mapSceneToView(last_scene_position)
        delta_x = previous_x.x() - current_x.x()
        delta_y = previous_y.y() - current_y.y()
        if x_target is y_target:
            x_target.translateBy(x=delta_x, y=delta_y)
        else:
            x_target.translateBy(x=delta_x)
            y_target.translateBy(y=delta_y)


class CursorLineLabel(pg.InfLineLabel):
    """Label that drags the cursor line instead of sliding along it."""

    def mouseDragEvent(self, ev: object) -> None:  # noqa: N802 - Qt override name.
        if ev.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        ev.accept()
        view_box = self.line.getViewBox()
        if view_box is None:
            return
        position = view_box.mapSceneToView(ev.scenePos())
        if self.line.angle % 180 == 90:
            self.line.setValue(position.x())
        else:
            self.line.setValue(position.y())


class WaveformPlot(QtWidgets.QWidget):
    cursorChanged = QtCore.Signal()
    viewRangeChanged = QtCore.Signal(tuple)
    activeAxisGroupChanged = QtCore.Signal(str)
    traceClicked = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.data: WaveformData | None = None
        self.selected_channels: set[str] = set()
        self.curves: dict[str, pg.PlotDataItem] = {}
        self.curve_groups: dict[str, str] = {}
        self.preview_curves: dict[str, pg.PlotDataItem] = {}
        self.preview_curve_groups: dict[str, str] = {}
        self.focused_channel: str | None = None
        self.opengl_available = _opengl_available()
        self.renderer_mode = "opengl" if self.opengl_available and _env_flag(OPENGL_ENV_VAR) else "cpu"
        self._syncing_region = False
        self._syncing_view = False
        self.active_y_group = "left"
        self.cursor_axis_group = "left"
        self._x_cursors_initialized = False
        self._y_cursors_initialized = False
        self.axis_settings: dict[str, AxisGroupSettings] = {}
        self._interaction_downsampling_active = False
        self._pending_preview_range: tuple[float, float] | None = None

        self._interaction_timer = QtCore.QTimer(self)
        self._interaction_timer.setSingleShot(True)
        self._interaction_timer.setInterval(INTERACTION_SETTLE_MS)
        self._interaction_timer.timeout.connect(self._restore_quality_downsampling)

        self._preview_range_timer = QtCore.QTimer(self)
        self._preview_range_timer.setSingleShot(True)
        self._preview_range_timer.setInterval(PREVIEW_RANGE_UPDATE_MS)
        self._preview_range_timer.timeout.connect(self._flush_pending_preview_range)

        self.view_box = WaveformViewBox(
            self.active_y_view_box,
            free_pan_getter=self._focused_trace_free_pan_enabled,
        )
        self.view_box.interactionStarted.connect(self._mark_interacting)
        self.plot = pg.PlotWidget(viewBox=self.view_box)
        self.plot_item = self.plot.getPlotItem()
        self.plot.setBackground(PLOT_BACKGROUND_COLOR)
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.legend = self.plot.addLegend(offset=(8, 8))
        self.plot.setLabel("bottom", "Time")
        self.plot.setMouseEnabled(x=True, y=True)
        self.plot_item.showAxis("right")

        self.right_view_box = WaveformViewBox(
            free_pan_getter=self._focused_trace_free_pan_enabled,
            x_target_getter=lambda: self.view_box,
        )
        self.right_view_box.interactionStarted.connect(self._mark_interacting)
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
        self.preview.viewport().installEventFilter(self)
        self.preview_item.showAxis("right")
        self.preview_item.getAxis("left").setPen(pg.mkPen(LEFT_AXIS_COLOR, width=1))
        self.preview_item.getAxis("left").setTextPen(pg.mkPen(LEFT_AXIS_COLOR))
        self.preview_item.getAxis("right").setPen(pg.mkPen(RIGHT_AXIS_COLOR, width=1))
        self.preview_item.getAxis("right").setTextPen(pg.mkPen(RIGHT_AXIS_COLOR))

        self.preview_right_view_box = pg.ViewBox()
        self.preview_right_view_box.setXLink(self.preview_item.vb)
        self.preview_right_view_box.setZValue(self.preview_item.vb.zValue() - 1)
        self.preview_right_view_box.setMouseEnabled(x=False, y=False)
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
            _cursor_line(angle=90, color="#ffffff", label="X1", label_position=0.96, label_anchor=(0, 0.5)),
            _cursor_line(angle=90, color="#aaaaaa", label="X2", label_position=0.90, label_anchor=(1, 0.5)),
        ]
        self.y_cursors = [
            _cursor_line(angle=0, color="#ffffff", label="Y1", label_position=0.04, label_anchor=(0.5, 1)),
            _cursor_line(angle=0, color="#aaaaaa", label="Y2", label_position=0.10, label_anchor=(0.5, 0)),
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
        self._apply_renderer_mode()
        self.update_axis_highlight()

    def set_renderer_mode(self, mode: str) -> bool:
        mode = "opengl" if mode == "opengl" else "cpu"
        if mode == "opengl" and not self.opengl_available:
            return False
        previous_mode = self.renderer_mode
        if mode == previous_mode:
            return True
        self.renderer_mode = mode
        if self._apply_renderer_mode():
            self._refresh_after_renderer_change()
            return True
        self.renderer_mode = previous_mode
        self._apply_renderer_mode()
        return False

    def _apply_renderer_mode(self) -> bool:
        use_opengl = self.renderer_mode == "opengl"
        try:
            self.plot.useOpenGL(use_opengl)
            self.preview.useOpenGL(use_opengl)
            self.preview.viewport().installEventFilter(self)
        except Exception as exc:  # noqa: BLE001 - keep experimental GPU mode from breaking startup.
            if use_opengl:
                self.opengl_available = False
                print(f"OpenGL rendering disabled: {exc}", file=sys.stderr)
            return False
        self._update_right_view_geometry()
        self._update_preview_right_view_geometry()
        return True

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:  # noqa: N802 - Qt override name.
        if watched is self.preview.viewport() and event.type() == QtCore.QEvent.Type.Wheel:
            self._zoom_preview_from_wheel(event)
            return True
        return super().eventFilter(watched, event)

    def _refresh_after_renderer_change(self) -> None:
        if self.data is None:
            return
        x_range = tuple(float(value) for value in self.view_box.viewRange()[0])
        group_y_ranges = {
            group: tuple(float(value) for value in self._view_box_for_group(group).viewRange()[1])
            for group in ("left", "right")
        }
        preview_x_range = tuple(float(value) for value in self.preview_item.vb.viewRange()[0])
        preview_y_ranges = {
            "left": tuple(float(value) for value in self.preview_item.vb.viewRange()[1]),
            "right": tuple(float(value) for value in self.preview_right_view_box.viewRange()[1]),
        }
        self._redraw()
        self.plot.setXRange(x_range[0], x_range[1], padding=0.0)
        self.preview.setXRange(preview_x_range[0], preview_x_range[1], padding=0.0)
        for group, y_range in group_y_ranges.items():
            self._view_box_for_group(group).setYRange(y_range[0], y_range[1], padding=0.0)
        self.preview_item.vb.setYRange(preview_y_ranges["left"][0], preview_y_ranges["left"][1], padding=0.0)
        self.preview_right_view_box.setYRange(preview_y_ranges["right"][0], preview_y_ranges["right"][1], padding=0.0)
        self._move_y_cursors_to_group(self.cursor_axis_group, preserve_visual_position=True)
        self._update_cursor_pens()
        self._flush_pending_preview_range()
        self.update()

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

    def replace_data_preserving_view(self, data: WaveformData, *, select: set[str] | None = None) -> None:
        x_range = tuple(float(value) for value in self.view_box.viewRange()[0])
        group_y_ranges = {
            group: tuple(float(value) for value in self._view_box_for_group(group).viewRange()[1])
            for group in ("left", "right")
        }
        previous_settings = self.axis_settings
        self.data = data
        self.axis_settings = {
            channel.name: previous_settings.get(
                channel.name,
                AxisGroupSettings(group="left", unit=channel.unit or ""),
            )
            for channel in data.channels
        }
        self.selected_channels.intersection_update({channel.name for channel in data.channels})
        if select is not None:
            self.selected_channels.update(select)
        if self.focused_channel not in self.selected_channels:
            self.focused_channel = None
        self._redraw()
        if np.isfinite(x_range).all() and x_range[0] != x_range[1]:
            self.plot.setXRange(x_range[0], x_range[1], padding=0.0)
            self.region.setRegion(x_range)
            self._set_preview_range_for_region(x_range[0], x_range[1])
        for group, y_range in group_y_ranges.items():
            if np.isfinite(y_range).all() and y_range[0] != y_range[1]:
                self._view_box_for_group(group).setYRange(y_range[0], y_range[1], padding=0.0)
        self.apply_axis_ranges(default_missing=True)
        self.update_axis_highlight()
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
        self.set_active_y_group("right" if self.active_y_group == "left" else "left")

    def set_active_y_group(self, group: str) -> None:
        group = "right" if group == "right" else "left"
        if group == self.active_y_group:
            return
        self.active_y_group = group
        self.update_axis_highlight()
        self.activeAxisGroupChanged.emit(self.active_y_group)

    def focus_channel(self, channel_name: str) -> None:
        if self.data is None or channel_name not in {channel.name for channel in self.data.channels}:
            return
        if channel_name not in self.selected_channels:
            self.selected_channels.add(channel_name)
            self._redraw()
        self.focused_channel = channel_name
        self.set_active_y_group(self._channel_group(channel_name))
        self._update_curve_focus()

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

    def x_cursor_range(self) -> tuple[float, float] | None:
        if not all(line.isVisible() for line in self.x_cursors):
            return None
        values = [self._line_value(line) for line in self.x_cursors]
        if values[0] is None or values[1] is None or values[0] == values[1]:
            return None
        return tuple(sorted((values[0], values[1])))

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
            _configure_curve_performance(curve, method=self._main_downsampling_method())
            self.legend.addItem(curve, self._legend_label(channel.name))
            preview_curve = pg.PlotDataItem(self.data.time[mask], channel.values[mask], pen=preview_pen)
            preview_curve.setZValue(CURVE_Z)
            if group == "right":
                self.preview_right_view_box.addItem(preview_curve)
            else:
                self.preview_item.addItem(preview_curve)
            _configure_curve_performance(preview_curve, method=PREVIEW_DOWNSAMPLE_METHOD)
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
            line.setPen(_cursor_pen(primary))
            line.label.setColor(primary)
        for line in self.x_cursors[1:] + self.y_cursors[1:]:
            line.setPen(_cursor_pen(secondary))
            line.label.setColor(secondary)

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
        self._schedule_preview_range_for_region(ranges[0], ranges[1])
        self._syncing_region = False
        self.viewRangeChanged.emit(tuple(float(value) for value in ranges))

    def _on_curve_clicked(self, channel_name: str, event: object) -> None:
        if hasattr(event, "accept"):
            event.accept()
        self.focused_channel = channel_name
        self.set_active_y_group(self._channel_group(channel_name))
        self._update_curve_focus()
        self.traceClicked.emit(channel_name)

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
        self._pending_preview_range = None
        self._preview_range_timer.stop()
        region_width = abs(high - low)
        if not np.isfinite(region_width) or region_width <= 0:
            return
        preview_width = region_width / PREVIEW_REGION_FRACTION
        center = (low + high) / 2.0
        preview_low = center - preview_width / 2.0
        preview_high = center + preview_width / 2.0
        self.preview.setXRange(preview_low, preview_high, padding=0.0)

    def _schedule_preview_range_for_region(self, low: float, high: float) -> None:
        self._pending_preview_range = (low, high)
        if not self._preview_range_timer.isActive():
            self._preview_range_timer.start()

    def _flush_pending_preview_range(self) -> None:
        if self._pending_preview_range is None:
            return
        low, high = self._pending_preview_range
        self._set_preview_range_for_region(low, high)

    def _zoom_preview_from_wheel(self, event: QtGui.QWheelEvent) -> None:
        delta = _wheel_delta(event)
        if delta == 0:
            event.ignore()
            return
        preview_low, preview_high = self.preview_item.vb.viewRange()[0]
        preview_width = preview_high - preview_low
        if not np.isfinite(preview_width) or preview_width <= 0:
            event.ignore()
            return

        region_low, region_high = self.region.getRegion()
        region_start_fraction = (region_low - preview_low) / preview_width
        region_end_fraction = (region_high - preview_low) / preview_width

        wheel_position = event.position().toPoint() if hasattr(event, "position") else event.pos()
        scene_position = self.preview.mapToScene(wheel_position)
        zoom_center = float(self.preview_item.vb.mapSceneToView(scene_position).x())
        if not np.isfinite(zoom_center):
            zoom_center = (preview_low + preview_high) / 2.0

        factor = PREVIEW_WHEEL_ZOOM_IN_FACTOR if delta > 0 else PREVIEW_WHEEL_ZOOM_OUT_FACTOR
        new_preview_low = zoom_center + (preview_low - zoom_center) * factor
        new_preview_high = zoom_center + (preview_high - zoom_center) * factor
        new_preview_width = new_preview_high - new_preview_low
        if not np.isfinite(new_preview_width) or new_preview_width <= 0:
            event.ignore()
            return

        new_region_low = new_preview_low + region_start_fraction * new_preview_width
        new_region_high = new_preview_low + region_end_fraction * new_preview_width
        if new_region_low == new_region_high:
            event.ignore()
            return

        self._pending_preview_range = None
        self._preview_range_timer.stop()
        self._syncing_view = True
        self._syncing_region = True
        self.preview.setXRange(new_preview_low, new_preview_high, padding=0.0)
        self.region.setRegion((new_region_low, new_region_high))
        self.plot.setXRange(new_region_low, new_region_high, padding=0.0)
        self._syncing_region = False
        self._syncing_view = False
        self.viewRangeChanged.emit((float(new_region_low), float(new_region_high)))
        event.accept()

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

    def _mark_interacting(self) -> None:
        if not self._interaction_downsampling_active:
            self._interaction_downsampling_active = True
            self._set_main_curve_downsampling(INTERACTION_DOWNSAMPLE_METHOD)
        self._interaction_timer.start()

    def _restore_quality_downsampling(self) -> None:
        if not self._interaction_downsampling_active:
            return
        self._interaction_downsampling_active = False
        self._set_main_curve_downsampling(MAIN_DOWNSAMPLE_METHOD)
        self._flush_pending_preview_range()

    def _set_main_curve_downsampling(self, method: str) -> None:
        for curve in self.curves.values():
            _set_curve_downsampling_method(curve, method)

    def _main_downsampling_method(self) -> str:
        return INTERACTION_DOWNSAMPLE_METHOD if self._interaction_downsampling_active else MAIN_DOWNSAMPLE_METHOD

    def _focused_trace_free_pan_enabled(self) -> bool:
        return self.focused_channel is not None

    def _legend_label(self, channel_name: str) -> str:
        return f"{channel_name} ({self._channel_group(channel_name)} axis)"

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


def _configure_curve_performance(curve: pg.PlotDataItem, *, method: str) -> None:
    curve.setClipToView(True)
    curve.setDownsampling(auto=True, method=method)
    curve.setSkipFiniteCheck(True)


def _set_curve_downsampling_method(curve: pg.PlotDataItem, method: str) -> None:
    if curve.opts.get("autoDownsample") is True and curve.opts.get("downsampleMethod") == method:
        return
    curve.setDownsampling(auto=True, method=method)


def _cursor_line(
    *,
    angle: int,
    color: str,
    label: str,
    label_position: float,
    label_anchor: tuple[float, float],
) -> pg.InfiniteLine:
    line = pg.InfiniteLine(
        angle=angle,
        movable=True,
        pen=_cursor_pen(color),
    )
    line.label = CursorLineLabel(
        line,
        text=label,
        **_cursor_label_opts(color, position=label_position, anchor=label_anchor),
    )
    line.label.setCursor(QtCore.Qt.CursorShape.SizeHorCursor if angle == 90 else QtCore.Qt.CursorShape.SizeVerCursor)
    return line


def _cursor_pen(color: str) -> QtGui.QPen:
    return pg.mkPen(color, width=CURSOR_WIDTH, style=QtCore.Qt.PenStyle.DashLine)


def _cursor_label_opts(color: str, *, position: float, anchor: tuple[float, float]) -> dict[str, object]:
    return {
        "position": position,
        "anchors": [anchor, anchor],
        "color": color,
        "fill": CURSOR_LABEL_FILL,
        "border": CURSOR_LABEL_BORDER,
    }


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _opengl_available() -> bool:
    try:
        from PySide6 import QtOpenGLWidgets

        widget = QtOpenGLWidgets.QOpenGLWidget()
        widget.deleteLater()
    except Exception:
        return False
    return True


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


def _wheel_axis_from_event(ev: object, axis: int | None) -> str:
    if axis == 0:
        return "x"
    if axis == 1:
        return "y"
    return "y" if _has_control_modifier(ev) else "x"


class SpectrumPlot(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.spectrum: SpectrumData | None = None
        self.frequency_range: tuple[float, float] | None = None
        self._display_frequency = np.array([], dtype=float)
        self._display_magnitude = np.array([], dtype=float)
        self.view_box = SpectrumViewBox()
        self.plot = pg.PlotWidget(viewBox=self.view_box)
        self.plot.setBackground(PLOT_BACKGROUND_COLOR)
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setLabel("bottom", "Frequency", units="Hz")
        self.plot.setLabel("left", "Magnitude", units="dB")
        self.plot.setMouseEnabled(x=True, y=True)
        self.curve = pg.PlotDataItem(pen=pg.mkPen("#ffd400", width=CURVE_WIDTH))
        self.plot.addItem(self.curve)
        self.hover_label = pg.TextItem(anchor=(0, 1), color="#ffffff", fill=CURSOR_LABEL_FILL)
        self.hover_label.setZValue(FOCUSED_CURVE_Z + 10)
        self.hover_label.hide()
        self.plot.addItem(self.hover_label)
        self._mouse_proxy = pg.SignalProxy(
            self.plot.scene().sigMouseMoved,
            rateLimit=30,
            slot=self._on_mouse_moved,
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot)

    def set_spectrum(self, spectrum: SpectrumData) -> None:
        self.spectrum = spectrum
        self.frequency_range = spectrum.frequency_range
        self._redraw(reset_view=True)

    def set_frequency_range(self, frequency_range: tuple[float, float]) -> None:
        self.frequency_range = tuple(sorted(frequency_range))
        self._redraw(reset_view=True)

    def clear(self) -> None:
        self.spectrum = None
        self.frequency_range = None
        self._display_frequency = np.array([], dtype=float)
        self._display_magnitude = np.array([], dtype=float)
        self.curve.setData([], [])
        self.hover_label.hide()

    def reset_view(self) -> None:
        self._redraw(reset_view=True)

    def _redraw(self, *, reset_view: bool = False) -> None:
        if self.spectrum is None:
            self.curve.setData([], [])
            return
        frequency_range = self.frequency_range or self.spectrum.frequency_range
        frequency, magnitude = filtered_spectrum(self.spectrum, frequency_range)
        magnitude_db = _magnitude_to_db(magnitude)
        self._display_frequency = frequency
        self._display_magnitude = magnitude_db
        self.curve.setData(frequency, magnitude_db)
        self.curve.setPen(pg.mkPen(self.spectrum.color, width=CURVE_WIDTH))
        x_low, x_high = _normalized_frequency_bounds(frequency_range)
        self.view_box.set_x_bounds(x_low, x_high)
        if x_high > x_low and reset_view:
            self.plot.setXRange(x_low, x_high, padding=0.0)
        finite_magnitude = magnitude_db[np.isfinite(magnitude_db)]
        if finite_magnitude.size and reset_view:
            y_max = float(np.nanmax(finite_magnitude))
            y_min = float(np.nanmin(finite_magnitude))
            if y_min == y_max:
                y_max = y_min + 1.0
            self.plot.setYRange(y_min, y_max, padding=0.08)
        self.view_box.clamp_x_to_bounds()

    def _on_mouse_moved(self, event: object) -> None:
        if self._display_frequency.size == 0 or self._display_magnitude.size == 0:
            self.hover_label.hide()
            return
        position = event[0] if isinstance(event, tuple) else event
        if not self.plot.sceneBoundingRect().contains(position):
            self.hover_label.hide()
            return
        point = self.plot.getPlotItem().vb.mapSceneToView(position)
        index = int(np.argmin(np.abs(self._display_frequency - point.x())))
        if not self._is_peak_index(index):
            self.hover_label.hide()
            return
        frequency = float(self._display_frequency[index])
        magnitude = float(self._display_magnitude[index])
        if not np.isfinite(frequency) or not np.isfinite(magnitude):
            self.hover_label.hide()
            return
        x_range, y_range = self.view_box.viewRange()
        tolerance_x = max((x_range[1] - x_range[0]) * 0.015, np.finfo(float).eps)
        tolerance_y = max((y_range[1] - y_range[0]) * 0.08, np.finfo(float).eps)
        if abs(point.x() - frequency) > tolerance_x or abs(point.y() - magnitude) > tolerance_y:
            self.hover_label.hide()
            return
        self.hover_label.setText(f"f={frequency:.8g} Hz\nMag={magnitude:.8g} dB")
        self.hover_label.setPos(frequency, magnitude)
        self.hover_label.show()

    def _is_peak_index(self, index: int) -> bool:
        if index <= 0 or index >= self._display_magnitude.size - 1:
            return self._display_magnitude.size <= 2
        value = self._display_magnitude[index]
        return bool(value >= self._display_magnitude[index - 1] and value >= self._display_magnitude[index + 1])


class SpectrumViewBox(pg.ViewBox):
    """Spectrum navigation mirrors waveform X/Y gestures, with frequency bounded at zero."""

    def __init__(self) -> None:
        super().__init__()
        self._x_bounds: tuple[float, float | None] = (0.0, None)

    def set_x_bounds(self, low: float, high: float | None) -> None:
        low = max(0.0, float(low)) if np.isfinite(low) else 0.0
        high = float(high) if high is not None and np.isfinite(high) else None
        if high is not None and high < low:
            high = low
        self._x_bounds = (low, high)
        if high is None:
            self.setLimits(xMin=low)
        else:
            self.setLimits(xMin=low, xMax=high)
        self.clamp_x_to_bounds()

    def wheelEvent(self, ev: QtGui.QWheelEvent, axis: int | None = None) -> None:  # noqa: N802 - Qt override name.
        zoom_axis = _wheel_axis_from_event(ev, axis)
        delta = _wheel_delta(ev)
        if delta == 0:
            ev.ignore()
            return
        scene_position = None
        if hasattr(ev, "scenePosition"):
            scene_position = ev.scenePosition()
        elif hasattr(ev, "scenePos"):
            scene_position = ev.scenePos()
        center = self.mapSceneToView(scene_position) if scene_position is not None else None
        factor = 0.8 if delta > 0 else 1.25
        if zoom_axis == "y":
            self.scaleBy(y=factor, center=center)
        else:
            self.scaleBy(x=factor, center=center)
        self.clamp_x_to_bounds()
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
        self.clamp_x_to_bounds()

    def clamp_to_non_negative(self) -> None:
        self.clamp_x_to_bounds()

    def clamp_x_to_non_negative(self) -> None:
        self.clamp_x_to_bounds()

    def clamp_x_to_bounds(self) -> None:
        x_range, _y_range = self.viewRange()
        x_low, x_high = x_range
        bound_low, bound_high = self._x_bounds
        if bound_high is None:
            if x_low < bound_low:
                self.setXRange(bound_low, bound_low + max(0.0, x_high - x_low), padding=0.0)
            return
        width = max(0.0, x_high - x_low)
        bounds_width = max(0.0, bound_high - bound_low)
        if width >= bounds_width:
            self.setXRange(bound_low, bound_high, padding=0.0)
        elif x_low < bound_low:
            self.setXRange(bound_low, bound_low + width, padding=0.0)
        elif x_high > bound_high:
            self.setXRange(bound_high - width, bound_high, padding=0.0)


def _magnitude_to_db(magnitude: np.ndarray) -> np.ndarray:
    values = np.asarray(magnitude, dtype=float)
    floor = np.finfo(float).tiny
    with np.errstate(divide="ignore", invalid="ignore"):
        return 20.0 * np.log10(np.maximum(values, floor))


def _normalized_frequency_bounds(frequency_range: tuple[float, float]) -> tuple[float, float]:
    low, high = sorted((float(frequency_range[0]), float(frequency_range[1])))
    low = max(0.0, low) if np.isfinite(low) else 0.0
    high = max(low, high) if np.isfinite(high) else low
    return low, high
