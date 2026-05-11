from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pyqtgraph as pg
import pytest

from csv_loader import ChannelData, WaveformData
from plot_widgets import AxisGroupSettings, OPENGL_ENV_VAR, WaveformPlot, _env_flag, _magnitude_to_db
from PySide6 import QtCore, QtWidgets


def test_axis_group_change_recalculates_main_and_preview_y_ranges(tmp_path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    plot = WaveformPlot()
    data = WaveformData(
        time=np.array([0.0, 1.0, 2.0]),
        channels=[
            ChannelData("voltage", np.array([0.0, 1.0, 2.0]), "#ffd400", "V"),
            ChannelData("current", np.array([100.0, 200.0, 300.0]), "#00d7ff", "A"),
        ],
        ignored_columns=[],
        source_path=tmp_path / "wave.csv",
        time_column="time",
    )
    plot.set_data(data)

    plot.update_axis_settings(
        {
            "voltage": AxisGroupSettings("left", "V", 0.0, 2.0),
            "current": AxisGroupSettings("left", "A", 100.0, 300.0),
        }
    )

    main_low, main_high = plot.view_box.viewRange()[1]
    preview_low, preview_high = plot.preview_item.vb.viewRange()[1]

    assert main_low <= 0.0
    assert main_high >= 300.0
    assert preview_low <= 0.0
    assert preview_high >= 300.0


def test_reset_view_uses_only_visible_enabled_waveforms_for_y_ranges(tmp_path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    plot = WaveformPlot()
    data = WaveformData(
        time=np.arange(4.0),
        channels=[
            ChannelData("visible", np.array([0.0, 1.0, 2.0, 3.0]), "#ffd400", "V"),
            ChannelData("hidden", np.array([1000.0, 1001.0, 1002.0, 1003.0]), "#00d7ff", "V"),
            ChannelData("disabled", np.array([-1000.0, -1001.0, -1002.0, -1003.0]), "#ff40ff", "V"),
        ],
        ignored_columns=[],
        source_path=tmp_path / "wave.csv",
        time_column="time",
    )
    plot.set_data(data)
    plot.update_axis_settings(
        {
            "visible": AxisGroupSettings("left", "V"),
            "hidden": AxisGroupSettings("left", "V"),
            "disabled": AxisGroupSettings("disabled", "V"),
        }
    )
    plot.set_selected_channels({"visible"})
    plot.view_box.setYRange(-5000.0, 5000.0, padding=0.0)

    plot.reset_view()

    low, high = plot.view_box.viewRange()[1]
    preview_low, preview_high = plot.preview_item.vb.viewRange()[1]

    assert low < 0.0
    assert high < 10.0
    assert preview_low < 0.0
    assert preview_high < 10.0


def test_reset_view_x_range_uses_finite_samples_from_visible_waveforms(tmp_path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    plot = WaveformPlot()
    data = WaveformData(
        time=np.arange(5.0),
        channels=[
            ChannelData("visible", np.array([np.nan, 1.0, 2.0, 3.0, np.nan]), "#ffd400", "V"),
            ChannelData("hidden", np.array([100.0, np.nan, np.nan, np.nan, 100.0]), "#00d7ff", "V"),
        ],
        ignored_columns=[],
        source_path=tmp_path / "wave.csv",
        time_column="time",
    )
    plot.set_data(data)
    plot.set_selected_channels({"visible"})
    plot.plot.setXRange(-10.0, 10.0, padding=0.0)

    plot.reset_view()

    low, high = plot.view_box.viewRange()[0]

    assert low == pytest.approx(1.0)
    assert high == pytest.approx(3.0)


def test_focused_trace_keeps_other_traces_opaque_and_curves_optimized(tmp_path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    plot = WaveformPlot()
    data = WaveformData(
        time=np.arange(20.0),
        channels=[
            ChannelData("voltage", np.linspace(0.0, 2.0, 20), "#ffd400", "V"),
            ChannelData("current", np.linspace(100.0, 300.0, 20), "#00d7ff", "A"),
        ],
        ignored_columns=[],
        source_path=tmp_path / "wave.csv",
        time_column="time",
    )
    plot.set_data(data)

    plot._on_curve_clicked("voltage", object())

    assert plot.curves["voltage"].zValue() > plot.curves["current"].zValue()
    assert plot.curves["current"].opts["pen"].color().alpha() == 255
    assert plot.curves["voltage"].opts["clipToView"] is True
    assert plot.curves["voltage"].opts["autoDownsample"] is True
    assert plot.curves["voltage"].opts["downsampleMethod"] == "peak"
    assert plot.curves["voltage"].opts["skipFiniteCheck"] is True


def test_curve_click_emits_trace_clicked_signal(tmp_path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    plot = WaveformPlot()
    data = WaveformData(
        time=np.arange(3.0),
        channels=[ChannelData("voltage", np.array([0.0, 1.0, 2.0]), "#ffd400", "V")],
        ignored_columns=[],
        source_path=tmp_path / "wave.csv",
        time_column="time",
    )
    plot.set_data(data)
    clicked: list[str] = []
    plot.traceClicked.connect(clicked.append)

    plot._on_curve_clicked("voltage", object())

    assert clicked == ["voltage"]


def test_interaction_uses_fast_downsampling_and_preview_is_throttled(tmp_path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    plot = WaveformPlot()
    data = WaveformData(
        time=np.arange(20.0),
        channels=[
            ChannelData("voltage", np.linspace(0.0, 2.0, 20), "#ffd400", "V"),
            ChannelData("current", np.linspace(100.0, 300.0, 20), "#00d7ff", "A"),
        ],
        ignored_columns=[],
        source_path=tmp_path / "wave.csv",
        time_column="time",
    )
    plot.set_data(data)

    plot._mark_interacting()

    assert plot.curves["voltage"].opts["downsampleMethod"] == "subsample"
    assert plot.preview_curves["voltage"].opts["downsampleMethod"] == "subsample"

    plot._schedule_preview_range_for_region(0.0, 10.0)
    assert plot._pending_preview_range == (0.0, 10.0)

    plot._restore_quality_downsampling()

    assert plot.curves["voltage"].opts["downsampleMethod"] == "peak"
    assert plot.preview_curves["voltage"].opts["downsampleMethod"] == "subsample"
    assert plot._pending_preview_range is None


def test_opengl_env_flag_is_opt_in(monkeypatch) -> None:
    monkeypatch.delenv(OPENGL_ENV_VAR, raising=False)
    assert _env_flag(OPENGL_ENV_VAR) is False

    monkeypatch.setenv(OPENGL_ENV_VAR, "1")
    assert _env_flag(OPENGL_ENV_VAR) is True

    monkeypatch.setenv(OPENGL_ENV_VAR, "false")
    assert _env_flag(OPENGL_ENV_VAR) is False


def test_magnitude_to_db_uses_amplitude_db_and_finite_floor() -> None:
    values = _magnitude_to_db(np.array([1.0, 10.0, 0.0]))

    assert values[0] == pytest.approx(0.0)
    assert values[1] == pytest.approx(20.0)
    assert np.isfinite(values[2])
    assert values[2] < -6000.0


def test_renderer_mode_rejects_unavailable_opengl(tmp_path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    plot = WaveformPlot()
    plot.opengl_available = False

    assert plot.set_renderer_mode("opengl") is False
    assert plot.renderer_mode == "cpu"


def test_renderer_mode_accepts_cpu(tmp_path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    plot = WaveformPlot()

    assert plot.set_renderer_mode("cpu") is True
    assert plot.renderer_mode == "cpu"


def test_renderer_mode_change_rebuilds_curves_and_preserves_view(tmp_path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    plot = WaveformPlot()
    data = WaveformData(
        time=np.arange(20.0),
        channels=[
            ChannelData("voltage", np.linspace(0.0, 2.0, 20), "#ffd400", "V"),
            ChannelData("current", np.linspace(100.0, 300.0, 20), "#00d7ff", "A"),
        ],
        ignored_columns=[],
        source_path=tmp_path / "wave.csv",
        time_column="time",
    )
    plot.set_data(data)
    original_curve = plot.curves["voltage"]
    plot.plot.setXRange(2.0, 12.0, padding=0.0)

    plot.renderer_mode = "opengl"
    assert plot.set_renderer_mode("cpu") is True

    assert plot.curves["voltage"] is not original_curve
    assert plot.view_box.viewRange()[0] == pytest.approx([2.0, 12.0])


def test_focused_trace_enables_free_pan_and_legend_shows_axis_group(tmp_path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    plot = WaveformPlot()
    data = WaveformData(
        time=np.arange(20.0),
        channels=[
            ChannelData("voltage", np.linspace(0.0, 2.0, 20), "#ffd400", "V"),
            ChannelData("current", np.linspace(100.0, 300.0, 20), "#00d7ff", "A"),
        ],
        ignored_columns=[],
        source_path=tmp_path / "wave.csv",
        time_column="time",
    )
    plot.set_data(data)

    assert plot._focused_trace_free_pan_enabled() is False
    assert plot._legend_label("voltage") == "voltage (left axis)"
    assert plot._legend_label("current") == "current (right axis)"

    plot._on_curve_clicked("voltage", object())

    assert plot._focused_trace_free_pan_enabled() is True


def test_active_axis_group_signal_emits_on_change() -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    plot = WaveformPlot()
    changes: list[str] = []
    plot.activeAxisGroupChanged.connect(changes.append)

    plot.set_active_y_group("right")
    plot.set_active_y_group("right")
    plot.toggle_active_y_group()

    assert changes == ["right", "left"]


def test_preview_right_axis_mouse_zoom_is_disabled() -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    plot = WaveformPlot()

    assert plot.preview_right_view_box.state["mouseEnabled"] == [False, False]


def test_waveform_viewbox_accepts_axis_wheel_argument() -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    plot = WaveformPlot()
    event = _FakeWheelEvent(QtCore.QPointF(0.0, 0.0), 120)

    plot.view_box.wheelEvent(event, axis=1)

    assert event.accepted is True


def test_preview_wheel_zoom_preserves_region_visual_fraction(tmp_path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    plot = WaveformPlot()
    plot.resize(800, 600)
    data = WaveformData(
        time=np.arange(100.0),
        channels=[
            ChannelData("voltage", np.linspace(0.0, 2.0, 100), "#ffd400", "V"),
            ChannelData("current", np.linspace(100.0, 300.0, 100), "#00d7ff", "A"),
        ],
        ignored_columns=[],
        source_path=tmp_path / "wave.csv",
        time_column="time",
    )
    plot.set_data(data)
    plot.show()
    app.processEvents()

    old_preview_low, old_preview_high = plot.preview_item.vb.viewRange()[0]
    old_preview_width = old_preview_high - old_preview_low
    old_region_low, old_region_high = plot.region.getRegion()
    old_region_fractions = (
        (old_region_low - old_preview_low) / old_preview_width,
        (old_region_high - old_preview_low) / old_preview_width,
    )

    viewport_center = QtCore.QPointF(
        plot.preview.viewport().width() / 2.0,
        plot.preview.viewport().height() / 2.0,
    )
    plot._zoom_preview_from_wheel(_FakeWheelEvent(viewport_center, 120))

    new_preview_low, new_preview_high = plot.preview_item.vb.viewRange()[0]
    new_preview_width = new_preview_high - new_preview_low
    new_region_low, new_region_high = plot.region.getRegion()
    new_region_fractions = (
        (new_region_low - new_preview_low) / new_preview_width,
        (new_region_high - new_preview_low) / new_preview_width,
    )

    assert new_preview_width == pytest.approx(old_preview_width * 0.8)
    assert new_region_fractions == pytest.approx(old_region_fractions)
    assert plot.view_box.viewRange()[0] == pytest.approx([new_region_low, new_region_high])


def test_cursor_lines_have_visible_labels(tmp_path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    plot = WaveformPlot()
    data = WaveformData(
        time=np.arange(20.0),
        channels=[
            ChannelData("voltage", np.linspace(0.0, 2.0, 20), "#ffd400", "V"),
            ChannelData("current", np.linspace(100.0, 300.0, 20), "#00d7ff", "A"),
        ],
        ignored_columns=[],
        source_path=tmp_path / "wave.csv",
        time_column="time",
    )
    plot.set_data(data)

    cursor_labels = [
        line.label.textItem.toPlainText()
        for line in plot.x_cursors + plot.y_cursors
    ]
    assert cursor_labels == ["X1", "X2", "Y1", "Y2"]
    assert plot.x_cursors[0].label.anchors == [(0, 0.5), (0, 0.5)]
    assert plot.x_cursors[1].label.anchors == [(1, 0.5), (1, 0.5)]
    assert plot.y_cursors[0].label.anchors == [(0.5, 1), (0.5, 1)]
    assert plot.y_cursors[1].label.anchors == [(0.5, 0), (0.5, 0)]

    plot.set_x_cursors_visible(True)
    plot.set_y_cursors_visible(True)

    assert all(line.isVisible() for line in plot.x_cursors + plot.y_cursors)

    assert all(
        line.pen.style() == QtCore.Qt.PenStyle.DashLine
        for line in plot.x_cursors + plot.y_cursors
    )


def test_cursor_labels_drag_cursor_lines(tmp_path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    plot = WaveformPlot()
    data = WaveformData(
        time=np.arange(20.0),
        channels=[
            ChannelData("voltage", np.linspace(0.0, 2.0, 20), "#ffd400", "V"),
            ChannelData("current", np.linspace(100.0, 300.0, 20), "#00d7ff", "A"),
        ],
        ignored_columns=[],
        source_path=tmp_path / "wave.csv",
        time_column="time",
    )
    plot.set_data(data)
    plot.set_x_cursors_visible(True)
    plot.set_y_cursors_visible(True)

    target_x = 12.0
    target_x_scene = plot.view_box.mapViewToScene(pg.Point(target_x, 0.0))
    plot.x_cursors[0].label.mouseDragEvent(_FakeDragEvent(target_x_scene))

    target_y = 1.5
    target_y_scene = plot.view_box.mapViewToScene(pg.Point(0.0, target_y))
    plot.y_cursors[0].label.mouseDragEvent(_FakeDragEvent(target_y_scene))

    assert plot.x_cursors[0].value() == pytest.approx(target_x)
    assert plot.y_cursors[0].value() == pytest.approx(target_y)


class _FakeDragEvent:
    def __init__(self, scene_position: QtCore.QPointF) -> None:
        self._scene_position = scene_position
        self.accepted = False

    def button(self) -> QtCore.Qt.MouseButton:
        return QtCore.Qt.MouseButton.LeftButton

    def accept(self) -> None:
        self.accepted = True

    def scenePos(self) -> QtCore.QPointF:
        return self._scene_position


class _FakeWheelEvent:
    def __init__(self, position: QtCore.QPointF, delta: int) -> None:
        self._position = position
        self._delta = delta
        self.accepted = False
        self.ignored = False

    def angleDelta(self) -> QtCore.QPoint:
        return QtCore.QPoint(0, self._delta)

    def position(self) -> QtCore.QPointF:
        return self._position

    def accept(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.ignored = True
