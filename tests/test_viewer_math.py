from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
import pytest

from PySide6 import QtCore, QtGui, QtWidgets
from plot_widgets import AxisGroupSettings
from viewer import AxisSetupDialog, MainWindow, TimebaseSettings, _restart_command, _time_column_validation, _waveform_with_timebase


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


def test_operand_pick_buttons_use_clicked_waveform(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow()
    window.load_file(_write_wave_csv(tmp_path))
    _select_combo_data(window.math_function, "add")

    window._start_operand_pick("a", True)
    window.waveform_plot._on_curve_clicked("current", object())

    assert window.math_operand_a.currentText() == "current"
    assert window.pending_waveform_pick is None
    assert window.pick_operand_a.isChecked() is False

    window._start_operand_pick("b", True)
    window.waveform_plot._on_curve_clicked("voltage", object())

    assert window.math_operand_b.currentText() == "voltage"
    assert window.pick_operand_b.isChecked() is False


def test_measure_pick_button_uses_clicked_waveform(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow()
    window.load_file(_write_wave_csv(tmp_path))

    window._start_measure_pick(True)
    window.waveform_plot._on_curve_clicked("current", object())

    assert window.measure_channel.currentText() == "current"
    assert window.pending_waveform_pick is None
    assert window.pick_measure_channel.isChecked() is False


def test_cursor_pick_button_uses_clicked_waveform_and_axis_group(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow()
    window.load_file(_write_wave_csv(tmp_path))
    window._channel_axis_group_moved("voltage", "left")
    window._channel_axis_group_moved("current", "right")

    window._start_cursor_channel_pick(True)
    window.waveform_plot._on_curve_clicked("current", object())

    assert window.waveform_plot.cursor_axis_group == "right"
    assert window.cursor_axis_selector.currentData() == "right"
    assert window.active_channel.currentText() == "current"
    assert window.pending_waveform_pick is None
    assert window.pick_cursor_channel.isChecked() is False

    window._start_cursor_channel_pick(True)
    window.waveform_plot._on_curve_clicked("voltage", object())

    assert window.waveform_plot.cursor_axis_group == "left"
    assert window.cursor_axis_selector.currentData() == "left"
    assert window.active_channel.currentText() == "voltage"


def test_channels_panel_groups_waveforms_by_axis(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow()
    window.load_file(_write_wave_csv(tmp_path))

    window.waveform_plot.update_axis_settings(
        {
            "voltage": AxisGroupSettings("left", "V"),
            "current": AxisGroupSettings("right", "A"),
        }
    )
    window._sync_channel_checks()

    assert _channel_names_in_group(window, "left") == ["voltage"]
    assert _channel_names_in_group(window, "right") == ["current"]
    assert _channel_names_in_group(window, "disabled") == []
    assert window.channel_panel.empty_labels["disabled"].isHidden() is False

    window.waveform_plot.update_axis_settings(
        {
            "voltage": AxisGroupSettings("disabled", "V"),
            "current": AxisGroupSettings("right", "A"),
        }
    )
    window._sync_channel_checks()

    assert _channel_names_in_group(window, "left") == []
    assert _channel_names_in_group(window, "right") == ["current"]
    assert _channel_names_in_group(window, "disabled") == ["voltage"]
    assert window.channel_checks["voltage"].selection_enabled is False


def test_channel_axis_group_move_updates_plot_state(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow()
    window.load_file(_write_wave_csv(tmp_path))

    window._channel_axis_group_moved("voltage", "right")

    assert window.waveform_plot.axis_settings["voltage"].group == "right"
    assert _channel_names_in_group(window, "right") == ["voltage", "current"]
    assert "voltage" in window.waveform_plot.selected_channels

    window._channel_axis_group_moved("voltage", "disabled")

    assert window.waveform_plot.axis_settings["voltage"].group == "disabled"
    assert _channel_names_in_group(window, "disabled") == ["voltage"]
    assert "voltage" not in window.waveform_plot.selected_channels
    assert window.channel_checks["voltage"].isChecked() is False

    window._channel_axis_group_moved("voltage", "left")

    assert window.waveform_plot.axis_settings["voltage"].group == "left"
    assert _channel_names_in_group(window, "left") == ["voltage"]
    assert "voltage" in window.waveform_plot.selected_channels


def test_right_side_tab_detaches_and_reattaches_on_close(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow()
    window.load_file(_write_wave_csv(tmp_path))
    tab = window.side_tabs.widget(2)

    window.side_tabs.detach_tab(2)
    app.processEvents()

    assert window.side_tabs.count() == 3
    assert window.side_tabs.indexOf(tab) == -1
    floating = window.side_tabs._detached_windows[tab]
    assert floating.layout().itemAt(0).widget() is tab
    assert tab.parent() is floating

    floating.close()
    app.processEvents()

    assert window.side_tabs.count() == 4
    assert window.side_tabs.widget(2) is tab
    assert window.side_tabs.currentWidget() is tab


def test_right_panel_restore_tab_shows_when_side_panel_collapsed(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow()
    window.load_file(_write_wave_csv(tmp_path))
    window.show()
    app.processEvents()
    window._update_side_panel_restore_tab()

    assert window.side_panel_restore_tab.isVisible() is False
    assert window.side_panel_restore_tab.text() == "^ Panel ^"

    window.splitter.setSizes([window.width(), 0])
    window._update_side_panel_restore_tab()
    app.processEvents()

    assert window.side_panel_restore_tab.isVisible() is True

    window.side_panel_restore_tab.click()
    app.processEvents()

    assert window.splitter.sizes()[1] > 8
    assert window.side_panel_restore_tab.isVisible() is False


def test_right_panel_forms_expand_fields_across_platforms(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow()
    window.load_file(_write_wave_csv(tmp_path))

    math_panel = window.side_tabs.widget(2)
    builder = math_panel.layout().itemAt(0).widget()
    spectrum_range = math_panel.layout().itemAt(1).widget()
    measure_panel = window.side_tabs.widget(3)
    measure_controls = measure_panel.layout().itemAt(0).widget()
    expected_policy = QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow

    assert builder.layout().fieldGrowthPolicy() == expected_policy
    assert spectrum_range.layout().fieldGrowthPolicy() == expected_policy
    assert measure_controls.layout().fieldGrowthPolicy() == expected_policy
    assert window.math_function.sizePolicy().horizontalPolicy() == QtWidgets.QSizePolicy.Policy.Expanding
    assert window.math_operand_a.sizePolicy().horizontalPolicy() == QtWidgets.QSizePolicy.Policy.Expanding
    assert window.pick_operand_a.sizePolicy().horizontalPolicy() == QtWidgets.QSizePolicy.Policy.Fixed
    assert window.pick_cursor_channel.sizePolicy().horizontalPolicy() == QtWidgets.QSizePolicy.Policy.Fixed
    assert window.pick_cursor_channel.sizeHint().width() > 0
    assert window.math_operand_a.parentWidget().layout().itemAt(0).alignment() == QtCore.Qt.AlignmentFlag.AlignVCenter
    assert window.math_operand_a.parentWidget().layout().itemAt(1).alignment() == QtCore.Qt.AlignmentFlag.AlignVCenter
    assert window.measure_channel.sizePolicy().horizontalPolicy() == QtWidgets.QSizePolicy.Policy.Expanding
    assert window.measure_channel.parentWidget().layout().itemAt(1).alignment() == QtCore.Qt.AlignmentFlag.AlignVCenter


def test_spectrum_range_only_visible_for_fft(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow()
    window.load_file(_write_wave_csv(tmp_path))

    _select_combo_data(window.math_function, "square")
    assert window.spectrum_range_box.isHidden() is True

    _select_combo_data(window.math_function, "fft")
    assert window.spectrum_range_box.isHidden() is False


def test_english_fallback_labels_and_stable_combo_ids(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow()
    window.load_file(_write_wave_csv(tmp_path))

    assert window.side_tabs.tabText(0) == "Channels"
    assert window.side_tabs.tabText(2) == "Math"
    assert window.plot_tabs.tabText(0) == "Waveforms"
    assert window.math_function.currentText()
    assert window.measure_range.itemText(0) == "Full waveform"
    assert set(window.axis_group_actions) == {"left", "right"}
    assert window.axis_group_actions["left"].text() == "Left"
    assert window.axis_group_actions["right"].text() == "Right"
    assert window.language_actions["system"].isChecked()
    assert "zh_CN" in window.language_actions
    assert window.language_actions["en"].text() == "English"
    assert window.language_actions["zh_CN"].text() == "\u4e2d\u6587"
    assert window.language_actions["ja_JP"].text() == "\u65e5\u672c\u8a9e"
    assert window.force_dark_mode_action.text() == "Force look"
    assert window.force_dark_mode_action.toolTip() == "Force the app style instead of using the system look"

    dialog = AxisSetupDialog(
        window.data,
        window.waveform_plot.axis_settings,
        window.waveform_plot.group_defaults(),
    )
    assert dialog.windowTitle() == "Waveform Setup"
    group_combo = dialog.table.cellWidget(0, dialog.GROUP_COLUMN)
    assert group_combo.itemData(0) == "left"
    assert group_combo.itemData(1) == "right"
    assert group_combo.itemData(2) == "disabled"


def test_language_selection_restarts_with_selected_language(tmp_path: Path, monkeypatch) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow(startup_language="system")
    window.load_file(_write_wave_csv(tmp_path))
    starts = []
    quits = []
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *args, **kwargs: QtWidgets.QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(QtCore.QProcess, "startDetached", lambda program, arguments: starts.append((program, arguments)) or True)
    monkeypatch.setattr(QtWidgets.QApplication, "quit", lambda: quits.append(True))

    window.language_actions["zh_CN"].trigger()

    assert starts
    assert starts[0][0] == sys.executable
    assert starts[0][1][1:3] == ["--language", "zh_CN"]
    assert str(window.source_data.source_path) in starts[0][1]
    assert quits == [True]


def test_restart_command_omits_script_path_for_frozen_app(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Program Files\cswave\cswave.exe")

    program, arguments = _restart_command("ja_JP")

    assert program == r"C:\Program Files\cswave\cswave.exe"
    assert arguments == ["--language", "ja_JP"]


def test_force_dark_mode_toggle_changes_application_palette(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow()
    window.load_file(_write_wave_csv(tmp_path))

    assert window.force_dark_mode_action.isChecked() is False

    window.force_dark_mode_action.setChecked(True)
    dark_window = app.palette().color(QtGui.QPalette.ColorRole.Window)

    assert dark_window.lightness() < 80

    window.force_dark_mode_action.setChecked(False)


def test_load_file_schedules_waveform_setup(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    opened = []
    window = MainWindow()
    window._open_waveform_setup = lambda: opened.append(window.data.source_path.name)

    window.load_file(_write_wave_csv(tmp_path), show_setup=True)
    app.processEvents()

    assert opened == ["wave.csv"]


def test_generated_timebase_treats_detected_time_as_signal(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow()
    window.load_file(_write_wave_csv(tmp_path))

    data = _waveform_with_timebase(window.source_data, TimebaseSettings("sample_rate", value=2.0))

    assert data.time_column is None
    assert data.timebase_kind == "sample_rate"
    assert data.timebase_value == 2.0
    assert data.time.tolist() == pytest.approx([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5])
    assert "time" in {channel.name for channel in data.channels}


def test_selected_time_column_is_validated_and_removed_from_signals(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    path = tmp_path / "wave.csv"
    path.write_text("A,B,C\n0,10,1\n1,20,2\n0.5,30,3\n", encoding="utf-8")
    window = MainWindow()
    window.load_file(path)

    dialog = AxisSetupDialog(
        window.data,
        window.waveform_plot.axis_settings,
        window.waveform_plot.group_defaults(),
    )
    dialog.timebase_mode.setCurrentIndex(dialog.timebase_mode.findData("column"))
    dialog.timebase_column.setCurrentText("A")

    assert dialog.buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).isEnabled() is False

    dialog.timebase_column.setCurrentText("B")
    assert dialog.buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).isEnabled() is True
    data = _waveform_with_timebase(window.source_data, dialog.timebase_settings())

    assert data.time.tolist() == [10.0, 20.0, 30.0]
    assert "B" not in {channel.name for channel in data.channels}
    assert {"A", "C"} == {channel.name for channel in data.channels}


def test_increasing_nonuniform_time_column_is_allowed_with_warning() -> None:
    values = np.array([0.0, 15e-9, 30e-9, 55e-9, 75e-9])

    valid, status = _time_column_validation(values)

    assert valid is True
    assert "nominal spacing" in status
    assert "FFT uses median spacing" in status


def test_measure_tab_reports_vertical_and_fft_horizontal_values(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow()
    window.load_file(_write_wave_csv(tmp_path))
    window.measure_channel.setCurrentText("voltage")
    window._update_measurements()

    assert window.measure_labels["max"].text() == "1"
    assert window.measure_labels["min"].text() == "-1"
    assert window.measure_labels["ptp"].text() == "2"
    assert float(window.measure_labels["rms"].text()) == pytest.approx(np.sqrt(0.5))
    assert float(window.measure_labels["acrms"].text()) == pytest.approx(np.sqrt(0.5))
    assert window.measure_labels["frequency"].text() == "0.25 Hz"
    assert window.measure_labels["period"].text() == "4 s"


def test_measure_tab_uses_x_cursor_range(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow()
    window.load_file(_write_wave_csv(tmp_path))
    window.measure_channel.setCurrentText("current")
    _select_combo_data(window.measure_range, "cursors")
    window.waveform_plot.set_x_cursors_visible(True)
    window.waveform_plot.x_cursors[0].setValue(2.0)
    window.waveform_plot.x_cursors[1].setValue(5.0)
    window._update_measurements()

    assert window.measure_labels["min"].text() == "2"
    assert window.measure_labels["max"].text() == "5"
    assert window.measure_labels["avg"].text() == "3.5"


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


def test_spectrum_plot_clamps_frequency_but_allows_negative_db(tmp_path: Path) -> None:
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
    assert window.spectrum_plot.view_box.viewRange()[1][0] == pytest.approx(-1.0)


def test_spectrum_plot_clamps_x_range_to_frequency_clip(tmp_path: Path) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _ = app
    window = MainWindow()
    window.load_file(_write_wave_csv(tmp_path))
    _select_combo_data(window.math_function, "fft")
    window.math_operand_a.setCurrentText("voltage")
    window.math_result_name.setText("fft-voltage")
    window._add_math_output()
    window.frequency_min.setText("0.125")
    window.frequency_max.setText("0.25")
    window._apply_frequency_range()

    window.spectrum_plot.view_box.setXRange(-1.0, 10.0, padding=0.0)
    window.spectrum_plot.view_box.clamp_x_to_bounds()

    assert window.spectrum_plot.view_box.viewRange()[0] == pytest.approx([0.125, 0.25])


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
    assert np.all(np.isfinite(window.spectrum_plot._display_magnitude))


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


def _channel_names_in_group(window: MainWindow, group: str) -> list[str]:
    layout = window.channel_panel.group_layouts[group]
    names = []
    for index in range(1, layout.count()):
        widget = layout.itemAt(index).widget()
        if isinstance(widget, QtWidgets.QCheckBox):
            names.append(widget.text())
    return names


def _channel_color(window: MainWindow, name: str) -> str:
    for channel in window.data.channels:
        if channel.name == name:
            return channel.color
    raise AssertionError(name)
