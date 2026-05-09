from __future__ import annotations

import numpy as np
import pytest

from csv_loader import ChannelData
from math_engine import (
    create_calculated_channel,
    create_fft_spectrum,
    filtered_spectrum,
    window_values,
    zero_padded_length,
)


def test_unary_and_binary_math_handles_invalid_values() -> None:
    a = ChannelData("A", np.array([1.0, -1.0, 4.0]), "#fff", "V")
    b = ChannelData("B", np.array([1.0, 0.0, 2.0]), "#0ff", "V")

    sqrt_trace = create_calculated_channel(function_id="sqrt", operand_a=a, operand_b=None, name="sqrt(A)", color="#f0f")
    div_trace = create_calculated_channel(function_id="divide", operand_a=a, operand_b=b, name="A/B", color="#f0f")
    add_trace = create_calculated_channel(function_id="add", operand_a=a, operand_b=b, name="A+B", color="#f0f")

    assert sqrt_trace.values[0] == pytest.approx(1.0)
    assert np.isnan(sqrt_trace.values[1])
    assert np.isinf(div_trace.values[1])
    assert add_trace.values.tolist() == [2.0, -1.0, 6.0]
    assert add_trace.unit == "V"
    assert add_trace.is_calculated is True


def test_fft_uses_full_time_range_and_reaches_nyquist() -> None:
    sample_rate = 16.0
    time = np.arange(16) / sample_rate
    signal = np.sin(2.0 * np.pi * 2.0 * time)
    channel = ChannelData("A", signal, "#fff")

    spectrum = create_fft_spectrum(channel=channel, time=time, name="FFT(A)")

    assert spectrum.time_range == pytest.approx((0.0, 15.0 / sample_rate))
    assert spectrum.frequency[-1] == pytest.approx(sample_rate / 2.0)
    assert spectrum.frequency[np.argmax(spectrum.magnitude)] == pytest.approx(2.0)


def test_fft_uses_selected_time_range() -> None:
    time = np.arange(10.0)
    channel = ChannelData("A", np.arange(10.0), "#fff")

    spectrum = create_fft_spectrum(channel=channel, time=time, name="FFT(A)", time_range=(6.0, 2.0))

    assert spectrum.time_range == pytest.approx((2.0, 6.0))
    assert spectrum.magnitude.size == 3


def test_frequency_filter_does_not_recompute_spectrum() -> None:
    time = np.arange(8.0)
    channel = ChannelData("A", np.arange(8.0), "#fff")
    spectrum = create_fft_spectrum(channel=channel, time=time, name="FFT(A)")

    frequency, magnitude = filtered_spectrum(spectrum, (0.125, 0.25))

    assert frequency.tolist() == [0.125, 0.25]
    assert magnitude.tolist() == spectrum.magnitude[1:3].tolist()


def test_fft_windows() -> None:
    assert window_values("rectangular", 4).tolist() == [1.0, 1.0, 1.0, 1.0]
    assert window_values("hann", 4).tolist() == pytest.approx(np.hanning(4).tolist())
    assert window_values("hamming", 4).tolist() == pytest.approx(np.hamming(4).tolist())
    assert window_values("cosine", 3).tolist() == pytest.approx([0.0, 1.0, 0.0])


def test_window_is_applied_before_fft() -> None:
    time = np.arange(4.0)
    channel = ChannelData("A", np.ones(4), "#fff")

    rectangular = create_fft_spectrum(channel=channel, time=time, name="FFT(A)", window_id="rectangular")
    hann = create_fft_spectrum(channel=channel, time=time, name="FFT(A)", window_id="hann")

    assert rectangular.magnitude[0] == pytest.approx(4.0)
    assert hann.magnitude[0] == pytest.approx(np.hanning(4).sum())


def test_fft_can_remove_dc_offset() -> None:
    time = np.arange(8.0)
    channel = ChannelData("A", np.full(8, 10.0), "#fff")

    with_dc = create_fft_spectrum(channel=channel, time=time, name="FFT(A)")
    without_dc = create_fft_spectrum(channel=channel, time=time, name="FFT(A)", remove_dc=True)

    assert with_dc.magnitude[0] == pytest.approx(80.0)
    assert without_dc.magnitude[0] == pytest.approx(0.0)


def test_fft_zero_padding_increases_bin_density_without_changing_nyquist() -> None:
    sample_rate = 8.0
    time = np.arange(8) / sample_rate
    channel = ChannelData("A", np.ones(8), "#fff")

    unpadded = create_fft_spectrum(channel=channel, time=time, name="FFT(A)")
    padded = create_fft_spectrum(channel=channel, time=time, name="FFT(A)", zero_pad="4x")

    assert zero_padded_length(5, "next_pow2") == 8
    assert unpadded.sample_count == 8
    assert unpadded.fft_count == 8
    assert padded.sample_count == 8
    assert padded.fft_count == 32
    assert padded.magnitude.size > unpadded.magnitude.size
    assert padded.frequency[-1] == pytest.approx(unpadded.frequency[-1])
    assert padded.frequency[1] - padded.frequency[0] == pytest.approx((unpadded.frequency[1] - unpadded.frequency[0]) / 4.0)
