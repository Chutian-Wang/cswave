from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

from csv_loader import ChannelData, WaveformData
from plot_widgets import AxisGroupSettings, WaveformPlot
from PySide6 import QtWidgets


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
    assert plot.curves["voltage"].opts["skipFiniteCheck"] is True
