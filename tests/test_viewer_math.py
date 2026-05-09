from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
import pytest

from PySide6 import QtCore, QtWidgets
from viewer import MainWindow


def test_calculated_trace_add_remove_updates_viewer_state(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow()
    window.load_file(_write_wave_csv(tmp_path))

    _select_combo_data(window.math_function, "add")
    window.math_operand_a.setCurrentText("voltage")
    window.math_operand_b.setCurrentText("current")
    window.math_result_name.setText("sum")

    window._add_math_output()

    assert "sum" in {channel.name for channel in window.data.channels}
    assert "sum" in window.channel_checks
    assert "sum" in window.waveform_plot.axis_settings
    assert "sum" in window.waveform_plot.selected_channels
    assert window.waveform_plot.curves["sum"] is not None

    matching = window.math_outputs.findItems("sum", QtCore.Qt.MatchFlag.MatchExactly)
    window.math_outputs.setCurrentItem(matching[0])
    assert window.plot_tabs.currentWidget() is window.waveform_plot
    assert window.waveform_plot.focused_channel == "sum"

    window.math_outputs.setCurrentItem(matching[0])
    window._remove_math_output()

    assert "sum" not in {channel.name for channel in window.data.channels}
    assert "sum" not in window.channel_checks
    assert "sum" not in window.waveform_plot.axis_settings


def test_fft_uses_x_cursors_window_and_frequency_range(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow()
    window.load_file(_write_wave_csv(tmp_path))
    window.waveform_plot.set_x_cursors_visible(True)
    window.waveform_plot.x_cursors[0].setValue(6.0)
    window.waveform_plot.x_cursors[1].setValue(2.0)

    _select_combo_data(window.math_function, "fft")
    _select_combo_data(window.fft_window, "hamming")
    window.math_operand_a.setCurrentText("voltage")
    window.math_result_name.setText("fft-voltage")

    window._add_math_output()

    spectrum = window.spectra["fft-voltage"]
    original_magnitude = spectrum.magnitude.copy()
    assert spectrum.time_range == (2.0, 6.0)
    assert spectrum.window_id == "hamming"
    assert spectrum.frequency_range == (0.0, spectrum.frequency[-1])
    assert spectrum.color == _channel_color(window, "voltage")
    assert window.spectrum_plot.curve.opts["pen"].color().name() == _channel_color(window, "voltage").lower()

    matching = window.math_outputs.findItems("fft-voltage", QtCore.Qt.MatchFlag.MatchExactly)
    window.math_outputs.setCurrentItem(matching[0])
    assert window.plot_tabs.currentWidget() is window.spectrum_plot

    window.frequency_min.setText("0")
    window.frequency_max.setText("0.25")
    window._apply_frequency_range()

    assert window.spectra["fft-voltage"].magnitude.tolist() == original_magnitude.tolist()
    assert window.spectrum_plot.frequency_range == (0.0, 0.25)


def test_update_fft_recalculates_points_window_and_dc_removal(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow()
    window.load_file(_write_wave_csv(tmp_path))
    window.waveform_plot.set_x_cursors_visible(True)
    window.waveform_plot.x_cursors[0].setValue(0.0)
    window.waveform_plot.x_cursors[1].setValue(7.0)

    _select_combo_data(window.math_function, "fft")
    _select_combo_data(window.fft_window, "rectangular")
    _select_combo_data(window.fft_zero_pad, "none")
    window.math_operand_a.setCurrentText("current")
    window.math_result_name.setText("fft-current")
    window._add_math_output()

    original = window.spectra["fft-current"]
    window.waveform_plot.x_cursors[0].setValue(2.0)
    window.waveform_plot.x_cursors[1].setValue(5.0)
    _select_combo_data(window.fft_window, "hann")
    _select_combo_data(window.fft_zero_pad, "4x")
    window.fft_remove_dc.setChecked(True)
    window._update_fft_spectrum()

    updated = window.spectra["fft-current"]
    assert updated.time_range == (2.0, 5.0)
    assert updated.window_id == "hann"
    assert updated.remove_dc is True
    assert updated.zero_pad == "4x"
    assert updated.sample_count == 4
    assert updated.fft_count == 16
    assert updated.magnitude.size != original.magnitude.size
    assert updated.magnitude[0] == pytest.approx(0.0)


def test_reset_view_only_affects_active_plot_tab(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow()
    window.load_file(_write_wave_csv(tmp_path))
    _select_combo_data(window.math_function, "fft")
    window.math_operand_a.setCurrentText("voltage")
    window.math_result_name.setText("fft-voltage")
    window._add_math_output()

    window.waveform_plot.plot.setXRange(1.0, 2.0, padding=0.0)
    window.spectrum_plot.plot.setXRange(0.1, 0.2, padding=0.0)
    window.plot_tabs.setCurrentWidget(window.spectrum_plot)
    window._reset_active_view()

    assert window.waveform_plot.view_box.viewRange()[0] == pytest.approx([1.0, 2.0])
    assert window.spectrum_plot.view_box.viewRange()[0][0] >= 0.0
    assert window.spectrum_plot.view_box.viewRange()[1][0] >= 0.0


def test_spectrum_plot_clamps_negative_ranges(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow()
    window.load_file(_write_wave_csv(tmp_path))
    _select_combo_data(window.math_function, "fft")
    window.math_operand_a.setCurrentText("voltage")
    window.math_result_name.setText("fft-voltage")
    window._add_math_output()

    window.spectrum_plot.view_box.setXRange(-1.0, 1.0, padding=0.0)
    window.spectrum_plot.view_box.setYRange(-1.0, 1.0, padding=0.0)
    window.spectrum_plot.view_box.clamp_to_non_negative()

    assert window.spectrum_plot.view_box.viewRange()[0][0] == pytest.approx(0.0)
    assert window.spectrum_plot.view_box.viewRange()[1][0] == pytest.approx(0.0)


def test_spectrum_peak_detection_for_hover_readout(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow()
    window.load_file(_write_wave_csv(tmp_path))
    _select_combo_data(window.math_function, "fft")
    window.math_operand_a.setCurrentText("voltage")
    window.math_result_name.setText("fft-voltage")
    window._add_math_output()

    peak_index = int(np.argmax(window.spectrum_plot._display_magnitude))

    assert window.spectrum_plot._is_peak_index(peak_index) is True


def test_load_file_asks_for_excel_sheet_when_multiple_sheets(tmp_path: Path, monkeypatch) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    path = tmp_path / "wave.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"time": [0.0, 1.0], "ignored": ["x", "y"]}).to_excel(writer, sheet_name="Notes", index=False)
        pd.DataFrame({"time": [0.0, 1.0], "voltage": [1.0, 2.0]}).to_excel(writer, sheet_name="Wave", index=False)
    choices = []

    def fake_get_item(parent, title, label, items, current, editable):
        _ = parent, title, label, current, editable
        choices.extend(items)
        return "Wave", True

    monkeypatch.setattr(QtWidgets.QInputDialog, "getItem", fake_get_item)
    window = MainWindow()
    window.load_file(path)

    assert choices == ["Notes", "Wave"]
    assert window.data.sheet_name == "Wave"
    assert [channel.name for channel in window.data.channels] == ["voltage"]


def _write_wave_csv(tmp_path: Path) -> Path:
    path = tmp_path / "wave.csv"
    time = np.arange(8.0)
    voltage = np.sin(2.0 * np.pi * 0.25 * time)
    current = np.arange(8.0)
    rows = ["time,voltage,current"]
    rows.extend(f"{t},{v},{i}" for t, v, i in zip(time, voltage, current, strict=True))
    path.write_text("\n".join(rows), encoding="utf-8")
    return path


def _select_combo_data(combo: QtWidgets.QComboBox, value: str) -> None:
    index = combo.findData(value)
    assert index >= 0
    combo.setCurrentIndex(index)


def _channel_color(window: MainWindow, name: str) -> str:
    for channel in window.data.channels:
        if channel.name == name:
            return channel.color
    raise AssertionError(name)
