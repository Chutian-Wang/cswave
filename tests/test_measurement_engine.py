from __future__ import annotations

import numpy as np
import pytest

from csv_loader import ChannelData
from measurement_engine import (
    cache_key,
    horizontal_measurements,
    selected_finite_values,
    vertical_measurements,
)


def test_vertical_measurements_use_full_finite_range() -> None:
    time = np.arange(5.0)
    channel = ChannelData("A", np.array([1.0, np.nan, 3.0, -1.0, 5.0]), "#fff", "V")

    result = vertical_measurements(channel=channel, time=time)

    assert result.max == 5.0
    assert result.min == -1.0
    assert result.avg == 2.0
    assert result.ptp == 6.0
    assert result.rms == pytest.approx(np.sqrt(9.0))
    assert result.acrms == pytest.approx(np.sqrt(5.0))


def test_cursor_range_selection_uses_monotonic_time_bounds() -> None:
    time = np.arange(10.0)
    channel = ChannelData("A", np.arange(10.0), "#fff")

    values = selected_finite_values(channel=channel, time=time, range_id="cursors", time_range=(6.0, 2.0))

    assert values.tolist() == [2.0, 3.0, 4.0, 5.0, 6.0]


def test_cursor_range_selection_filters_non_finite_values() -> None:
    time = np.array([0.0, 1.0, np.nan, 3.0, 4.0])
    channel = ChannelData("A", np.array([0.0, 1.0, 2.0, np.inf, 4.0]), "#fff")

    values = selected_finite_values(channel=channel, time=time, range_id="full", time_range=None)

    assert values.tolist() == [0.0, 1.0, 4.0]


def test_horizontal_measurements_report_peak_frequency() -> None:
    sample_rate = 16.0
    time = np.arange(64) / sample_rate
    channel = ChannelData("A", np.sin(2.0 * np.pi * 2.0 * time), "#fff")

    result = horizontal_measurements(channel=channel, time=time)

    assert result.frequency == pytest.approx(2.0)
    assert result.period == pytest.approx(0.5)


def test_measurement_cache_key_tracks_range_and_array_identity() -> None:
    time = np.arange(5.0)
    channel = ChannelData("A", np.arange(5.0), "#fff")

    full = cache_key(channel=channel, time=time, range_id="full", time_range=None)
    ranged = cache_key(channel=channel, time=time, range_id="cursors", time_range=(3.0, 1.0))

    assert full.channel_name == "A"
    assert full.time_id == id(time)
    assert full.values_id == id(channel.values)
    assert full.low is None
    assert ranged.low == 1.0
    assert ranged.high == 3.0
