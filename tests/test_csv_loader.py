from __future__ import annotations

from pathlib import Path

import numpy as np

from csv_loader import load_csv_waveform


def write_csv(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_loads_example_csv_and_detects_timeoutput() -> None:
    data = load_csv_waveform("example_csv/1t1r_set_read_0P1V.csv")

    assert data.time_column == "TimeOutput"
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
