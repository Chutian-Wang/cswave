from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from csv_loader import ChannelData
from math_engine import create_fft_spectrum


@dataclass(frozen=True)
class MeasurementResult:
    max: float | None = None
    min: float | None = None
    avg: float | None = None
    ptp: float | None = None
    rms: float | None = None
    acrms: float | None = None
    period: float | None = None
    frequency: float | None = None

    def as_dict(self) -> dict[str, float | None]:
        return {
            "max": self.max,
            "min": self.min,
            "avg": self.avg,
            "ptp": self.ptp,
            "rms": self.rms,
            "acrms": self.acrms,
            "period": self.period,
            "frequency": self.frequency,
        }


@dataclass(frozen=True)
class MeasurementCacheKey:
    channel_name: str
    time_id: int
    values_id: int
    range_id: str
    low: float | None
    high: float | None


def cache_key(
    *,
    channel: ChannelData,
    time: np.ndarray,
    range_id: str,
    time_range: tuple[float, float] | None,
) -> MeasurementCacheKey:
    low: float | None = None
    high: float | None = None
    if range_id == "cursors" and time_range is not None:
        low, high = sorted((float(time_range[0]), float(time_range[1])))
    return MeasurementCacheKey(channel.name, id(time), id(channel.values), range_id, low, high)


def vertical_measurements(
    *,
    channel: ChannelData,
    time: np.ndarray,
    range_id: str = "full",
    time_range: tuple[float, float] | None = None,
) -> MeasurementResult:
    selected_values = selected_finite_values(channel=channel, time=time, range_id=range_id, time_range=time_range)
    if selected_values.size == 0:
        return MeasurementResult()
    average = float(np.mean(selected_values))
    return MeasurementResult(
        max=float(np.max(selected_values)),
        min=float(np.min(selected_values)),
        avg=average,
        ptp=float(np.ptp(selected_values)),
        rms=float(np.sqrt(np.mean(np.square(selected_values)))),
        acrms=float(np.sqrt(np.mean(np.square(selected_values - average)))),
    )


def selected_finite_values(
    *,
    channel: ChannelData,
    time: np.ndarray,
    range_id: str,
    time_range: tuple[float, float] | None,
) -> np.ndarray:
    values = _as_float_view(channel.values)
    time_values = _as_float_view(time)
    if range_id == "cursors" and time_range is not None:
        low, high = sorted(time_range)
        if _is_monotonic_increasing(time_values):
            start = int(np.searchsorted(time_values, low, side="left"))
            stop = int(np.searchsorted(time_values, high, side="right"))
            selected_time = time_values[start:stop]
            selected_values = values[start:stop]
            finite = np.isfinite(selected_time) & np.isfinite(selected_values)
            return selected_values[finite]
        range_mask = (time_values >= low) & (time_values <= high)
    else:
        range_mask = slice(None)
    selected_time = time_values[range_mask]
    selected_values = values[range_mask]
    finite = np.isfinite(selected_time) & np.isfinite(selected_values)
    return selected_values[finite]


def horizontal_measurements(
    *,
    channel: ChannelData,
    time: np.ndarray,
    range_id: str = "full",
    time_range: tuple[float, float] | None = None,
) -> MeasurementResult:
    fft_range = time_range if range_id == "cursors" else None
    try:
        spectrum = create_fft_spectrum(
            channel=channel,
            time=time,
            name=f"Measure FFT({channel.name})",
            time_range=fft_range,
            window_id="rectangular",
            remove_dc=True,
            zero_pad="next_pow2",
        )
    except Exception:
        return MeasurementResult()
    if spectrum.frequency.size < 2:
        return MeasurementResult()
    frequency = spectrum.frequency[1:]
    magnitude = spectrum.magnitude[1:]
    finite = np.isfinite(frequency) & np.isfinite(magnitude)
    if not np.any(finite):
        return MeasurementResult()
    frequency = frequency[finite]
    magnitude = magnitude[finite]
    peak_frequency = float(frequency[int(np.argmax(magnitude))])
    if not np.isfinite(peak_frequency) or peak_frequency <= 0:
        return MeasurementResult()
    return MeasurementResult(frequency=peak_frequency, period=1.0 / peak_frequency)


def merge_measurements(vertical: MeasurementResult, horizontal: MeasurementResult | None) -> MeasurementResult:
    if horizontal is None:
        return vertical
    return MeasurementResult(
        max=vertical.max,
        min=vertical.min,
        avg=vertical.avg,
        ptp=vertical.ptp,
        rms=vertical.rms,
        acrms=vertical.acrms,
        period=horizontal.period,
        frequency=horizontal.frequency,
    )


def _as_float_view(values: np.ndarray) -> np.ndarray:
    if np.issubdtype(values.dtype, np.floating):
        return values
    return values.astype(float)


def _is_monotonic_increasing(values: np.ndarray) -> bool:
    if values.size < 2:
        return True
    return bool(np.all(values[1:] >= values[:-1]))
