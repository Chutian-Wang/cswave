from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import numpy as np

import pandas as pd

from csv_loader import excel_sheet_names, load_csv_waveform, load_waveform


def write_csv(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_loads_example_csv_and_detects_timeoutput() -> None:
    data = load_csv_waveform("example_csv/1t1r_set_read_0P1V.csv")

    assert data.time_column == "TimeOutput"
    assert data.timebase_kind == "column"
    assert "TimeOutput" in data.time_candidates
    assert len(data.time) == 22260
    assert {"VMeasCh1", "IMeasCh1", "VMeasCh2", "IMeasCh2", "G", "R"}.issubset(
        {channel.name for channel in data.channels}
    )
    assert "StatusCh1" in data.ignored_columns
    assert np.isfinite(data.time).all()


def test_falls_back_to_sample_index_without_time_column(tmp_path: Path) -> None:
    csv_path = write_csv(
        tmp_path / "wave.csv",
        "A,B\n1,10\n2,20\n3,30\n",
    )

    data = load_csv_waveform(csv_path)

    assert data.time_column is None
    assert data.timebase_kind == "sample_index"
    assert set(data.time_candidates) == {"A", "B"}
    assert data.time.tolist() == [0.0, 1.0, 2.0]
    assert [channel.name for channel in data.channels] == ["A", "B"]


def test_ignores_text_and_empty_columns(tmp_path: Path) -> None:
    csv_path = write_csv(
        tmp_path / "wave.csv",
        "time,signal,status,empty\n0,1,OK,\n1,2,FAIL,\n2,3,OK,\n",
    )

    data = load_csv_waveform(csv_path)

    assert data.time_column == "time"
    assert [channel.name for channel in data.channels] == ["signal"]
    assert set(data.ignored_columns) == {"status", "empty"}


def test_partially_invalid_numeric_channel_threshold(tmp_path: Path) -> None:
    csv_path = write_csv(
        tmp_path / "wave.csv",
        "time,keep,drop\n0,1,1\n1,bad,bad\n2,3,bad\n3,4,bad\n",
    )

    data = load_csv_waveform(csv_path)

    assert [channel.name for channel in data.channels] == ["keep"]
    assert "drop" in data.ignored_columns


def test_strips_bom_from_headers(tmp_path: Path) -> None:
    csv_path = tmp_path / "bom.csv"
    csv_path.write_text("\ufeffTimeOutput,V\n0,1\n1,2\n", encoding="utf-8")

    data = load_csv_waveform(csv_path)

    assert data.time_column == "TimeOutput"
    assert [channel.name for channel in data.channels] == ["V"]


def test_main_imports_with_windows_python_312_import_order() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import main; print('ok')"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_loads_excel_waveform_sheet(tmp_path: Path) -> None:
    xlsx_path = tmp_path / "wave.xlsx"
    with pd.ExcelWriter(xlsx_path) as writer:
        pd.DataFrame({"time": [0.0, 1.0], "A": [1.0, 2.0]}).to_excel(writer, sheet_name="Wave", index=False)
        pd.DataFrame({"note": ["not wave"]}).to_excel(writer, sheet_name="Notes", index=False)

    data = load_waveform(xlsx_path, sheet_name="Wave")

    assert excel_sheet_names(xlsx_path) == ["Wave", "Notes"]
    assert data.sheet_name == "Wave"
    assert data.time_column == "time"
    assert [channel.name for channel in data.channels] == ["A"]


def test_loads_example_xls_waveform(capsys) -> None:
    data = load_waveform("example_csv/Rectangular_gate_4.xls", sheet_name="Run203")

    assert data.sheet_name == "Run203"
    assert data.time_column == "TimeOutput"
    assert {"VMeasCh1", "IMeasCh1"}.issubset({channel.name for channel in data.channels})
    captured = capsys.readouterr()
    assert "OLE2 inconsistency" not in captured.out
    assert "OLE2 inconsistency" not in captured.err
