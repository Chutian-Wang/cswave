from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
import io
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


OSCILLOSCOPE_COLORS = [
    "#ffd400",  # yellow
    "#00d7ff",  # cyan
    "#ff40ff",  # magenta
    "#2dff68",  # green
    "#4a7dff",  # blue
    "#ff4040",  # red
    "#ff9f1a",  # orange
    "#d8d8d8",  # gray/white
]

TIME_NAME_PRIORITY = (
    "timeoutput",
    "time",
    "timestamp",
    "timestamps",
    "t",
    "seconds",
    "second",
    "sec",
    "s",
)


@dataclass(frozen=True)
class ChannelData:
    name: str
    values: np.ndarray
    color: str
    unit: str | None = None
    source_expression: str | None = None
    is_calculated: bool = False


@dataclass(frozen=True)
class WaveformData:
    time: np.ndarray
    channels: list[ChannelData]
    ignored_columns: list[str]
    source_path: Path
    time_column: str | None = None
    sheet_name: str | None = None
    time_candidates: dict[str, np.ndarray] | None = None
    timebase_kind: str = "sample_index"
    timebase_value: float | None = None


def load_csv_waveform(
    path: str | Path,
    *,
    finite_ratio_threshold: float = 0.5,
    min_finite_samples: int = 2,
) -> WaveformData:
    """Load a CSV file and infer the time column plus displayable channels."""
    source_path = Path(path)
    frame = pd.read_csv(source_path, encoding="utf-8-sig")
    return _waveform_from_frame(
        frame,
        source_path=source_path,
        sheet_name=None,
        finite_ratio_threshold=finite_ratio_threshold,
        min_finite_samples=min_finite_samples,
    )


def load_waveform(
    path: str | Path,
    *,
    sheet_name: str | int | None = None,
    finite_ratio_threshold: float = 0.5,
    min_finite_samples: int = 2,
) -> WaveformData:
    """Load CSV or Excel waveform data and infer the time column plus displayable channels."""
    source_path = Path(path)
    if source_path.suffix.lower() in {".xls", ".xlsx", ".xlsm"}:
        names = _excel_sheet_names(source_path)
        requested_sheet = sheet_name if sheet_name is not None else 0
        frame = _read_excel_quiet(source_path, requested_sheet)
        actual_sheet = names[sheet_name] if isinstance(sheet_name, int) and sheet_name < len(names) else sheet_name
        if actual_sheet is None:
            actual_sheet = names[0] if names else None
        return _waveform_from_frame(
            frame,
            source_path=source_path,
            sheet_name=str(actual_sheet) if actual_sheet is not None else None,
            finite_ratio_threshold=finite_ratio_threshold,
            min_finite_samples=min_finite_samples,
        )
    return load_csv_waveform(
        source_path,
        finite_ratio_threshold=finite_ratio_threshold,
        min_finite_samples=min_finite_samples,
    )


def excel_sheet_names(path: str | Path) -> list[str]:
    return _excel_sheet_names(Path(path))


def _waveform_from_frame(
    frame: pd.DataFrame,
    *,
    source_path: Path,
    sheet_name: str | None,
    finite_ratio_threshold: float,
    min_finite_samples: int,
) -> WaveformData:
    frame = frame.rename(columns={column: _clean_header(column) for column in frame.columns})

    numeric_columns = {
        column: _numeric_array(frame[column])
        for column in frame.columns
    }
    valid_columns = [
        column
        for column, values in numeric_columns.items()
        if _is_valid_numeric_channel(values, finite_ratio_threshold, min_finite_samples)
    ]

    time_column = _detect_time_column(valid_columns, numeric_columns)
    if time_column is None:
        time_values = np.arange(len(frame), dtype=float)
    else:
        time_values = numeric_columns[time_column].astype(float)

    channel_names: list[str] = []
    ignored_columns: list[str] = []
    for column in frame.columns:
        if column == time_column:
            continue
        values = numeric_columns[column]
        if column in valid_columns:
            channel_names.append(column)
        else:
            ignored_columns.append(column)

    channels = [
        ChannelData(
            name=name,
            values=numeric_columns[name].astype(float),
            color=OSCILLOSCOPE_COLORS[index % len(OSCILLOSCOPE_COLORS)],
            unit=_guess_unit(name),
        )
        for index, name in enumerate(channel_names)
    ]

    return WaveformData(
        time=time_values,
        channels=channels,
        ignored_columns=ignored_columns,
        source_path=source_path,
        time_column=time_column,
        sheet_name=sheet_name,
        time_candidates={
            name: numeric_columns[name].astype(float)
            for name in valid_columns
        },
        timebase_kind="column" if time_column is not None else "sample_index",
    )


def _excel_sheet_names(path: Path) -> list[str]:
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return list(pd.ExcelFile(path).sheet_names)


def _read_excel_quiet(path: Path, sheet_name: str | int) -> pd.DataFrame:
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return pd.read_excel(path, sheet_name=sheet_name)


def _clean_header(column: object) -> str:
    return str(column).replace("\ufeff", "").strip()


def _numeric_array(series: pd.Series) -> np.ndarray:
    return pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)


def _is_valid_numeric_channel(
    values: np.ndarray,
    finite_ratio_threshold: float,
    min_finite_samples: int,
) -> bool:
    if values.size == 0:
        return False
    finite_count = int(np.isfinite(values).sum())
    return finite_count >= min_finite_samples and finite_count / values.size >= finite_ratio_threshold


def _detect_time_column(
    valid_columns: Iterable[str],
    numeric_columns: dict[str, np.ndarray],
) -> str | None:
    valid_set = set(valid_columns)
    if not valid_set:
        return None

    normalized = {column: _normalize_name(column) for column in valid_set}
    for name in TIME_NAME_PRIORITY:
        for column, candidate in normalized.items():
            if candidate == name:
                return column

    for column, candidate in normalized.items():
        if "time" in candidate:
            return column

    monotonic_candidates = [
        column for column in valid_set
        if _finite_values(numeric_columns[column]).size >= 2
        and np.all(np.diff(_finite_values(numeric_columns[column])) >= 0)
    ]
    if len(monotonic_candidates) == 1:
        return monotonic_candidates[0]
    return None


def _finite_values(values: np.ndarray) -> np.ndarray:
    return values[np.isfinite(values)]


def _normalize_name(name: str) -> str:
    return "".join(character.lower() for character in name if character.isalnum())


def _guess_unit(name: str) -> str | None:
    lowered = name.lower()
    if lowered.startswith("v") or "voltage" in lowered:
        return "V"
    if lowered.startswith("i") or "current" in lowered:
        return "A"
    if lowered in {"r", "r_av"} or "resistance" in lowered:
        return "ohm"
    if lowered == "g" or "conductance" in lowered:
        return "S"
    return None
