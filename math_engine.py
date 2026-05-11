from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from csv_loader import ChannelData


ZERO_PAD_OPTIONS: tuple[tuple[str, str], ...] = (
    ("none", "None"),
    ("next_pow2", "Next power of 2"),
    ("2x", "2x"),
    ("4x", "4x"),
    ("8x", "8x"),
)


@dataclass(frozen=True)
class MathFunction:
    id: str
    label: str
    arity: int
    domain: str
    evaluator: Callable[..., np.ndarray]


@dataclass(frozen=True)
class WindowFunction:
    id: str
    label: str
    evaluator: Callable[[int], np.ndarray]


@dataclass(frozen=True)
class SpectrumData:
    name: str
    frequency: np.ndarray
    magnitude: np.ndarray
    source_channel: str
    color: str
    time_range: tuple[float, float]
    frequency_range: tuple[float, float]
    window_id: str
    remove_dc: bool = False
    zero_pad: str = "none"
    sample_count: int = 0
    fft_count: int = 0


def _unary_square(a: np.ndarray) -> np.ndarray:
    return np.square(a)


def _unary_sqrt(a: np.ndarray) -> np.ndarray:
    return np.sqrt(a)


def _unary_abs(a: np.ndarray) -> np.ndarray:
    return np.abs(a)


def _unary_log10(a: np.ndarray) -> np.ndarray:
    return np.log10(a)


def _unary_ln(a: np.ndarray) -> np.ndarray:
    return np.log(a)


def _unary_negate(a: np.ndarray) -> np.ndarray:
    return -a


def _binary_add(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return a + b


def _binary_subtract(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return a - b


def _binary_multiply(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return a * b


def _binary_divide(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return a / b


MATH_FUNCTIONS: tuple[MathFunction, ...] = (
    MathFunction("square", "A^2", 1, "time", _unary_square),
    MathFunction("sqrt", "sqrt(A)", 1, "time", _unary_sqrt),
    MathFunction("abs", "abs(A)", 1, "time", _unary_abs),
    MathFunction("log10", "log10(A)", 1, "time", _unary_log10),
    MathFunction("ln", "ln(A)", 1, "time", _unary_ln),
    MathFunction("negate", "-A", 1, "time", _unary_negate),
    MathFunction("add", "A+B", 2, "time", _binary_add),
    MathFunction("subtract", "A-B", 2, "time", _binary_subtract),
    MathFunction("multiply", "A*B", 2, "time", _binary_multiply),
    MathFunction("divide", "A/B", 2, "time", _binary_divide),
    MathFunction("fft", "FFT(A)", 1, "frequency", lambda a: a),
)

MATH_FUNCTION_BY_ID = {function.id: function for function in MATH_FUNCTIONS}


WINDOW_FUNCTIONS: tuple[WindowFunction, ...] = (
    WindowFunction("rectangular", "Rectangular", lambda count: np.ones(count, dtype=float)),
    WindowFunction("hann", "Hann", np.hanning),
    WindowFunction("hamming", "Hamming", np.hamming),
    WindowFunction("cosine", "Cosine", lambda count: np.sin(np.pi * np.arange(count, dtype=float) / max(count - 1, 1))),
)

WINDOW_FUNCTION_BY_ID = {function.id: function for function in WINDOW_FUNCTIONS}


def create_calculated_channel(
    *,
    function_id: str,
    operand_a: ChannelData,
    operand_b: ChannelData | None,
    name: str,
    color: str,
) -> ChannelData:
    function = MATH_FUNCTION_BY_ID[function_id]
    if function.domain != "time":
        raise ValueError(f"{function.label} does not create a time-domain trace")
    if function.arity == 2 and operand_b is None:
        raise ValueError(f"{function.label} requires two operands")
    if operand_b is not None and operand_a.values.shape != operand_b.values.shape:
        raise ValueError("Operands must have the same sample count")

    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        if function.arity == 1:
            values = function.evaluator(operand_a.values.astype(float))
            expression = function.label.replace("A", operand_a.name)
        else:
            values = function.evaluator(operand_a.values.astype(float), operand_b.values.astype(float))
            expression = function.label.replace("A", operand_a.name).replace("B", operand_b.name)

    return ChannelData(
        name=name,
        values=np.asarray(values, dtype=float),
        color=color,
        unit=_derived_unit(function_id, operand_a, operand_b),
        source_expression=expression,
        is_calculated=True,
    )


def create_fft_spectrum(
    *,
    channel: ChannelData,
    time: np.ndarray,
    name: str,
    time_range: tuple[float, float] | None = None,
    window_id: str = "rectangular",
    remove_dc: bool = False,
    zero_pad: str = "none",
) -> SpectrumData:
    finite_mask = np.isfinite(time) & np.isfinite(channel.values)
    selected_time = time[finite_mask].astype(float)
    selected_values = channel.values[finite_mask].astype(float)
    if time_range is not None:
        low, high = sorted(time_range)
        range_mask = (selected_time >= low) & (selected_time <= high)
        selected_time = selected_time[range_mask]
        selected_values = selected_values[range_mask]
    if selected_time.size < 2:
        raise ValueError("FFT requires at least two finite samples in the selected time range")

    order = np.argsort(selected_time)
    selected_time = selected_time[order]
    selected_values = selected_values[order]
    spacing = float(np.median(np.diff(selected_time)))
    if not np.isfinite(spacing) or spacing <= 0:
        raise ValueError("FFT requires a finite, increasing time base")

    if remove_dc:
        selected_values = selected_values - float(np.nanmean(selected_values))
    sample_count = int(selected_values.size)
    fft_count = zero_padded_length(sample_count, zero_pad)
    window = window_values(window_id, selected_values.size)
    windowed_values = selected_values * window
    if fft_count > sample_count:
        windowed_values = np.pad(windowed_values, (0, fft_count - sample_count), mode="constant")
    spectrum = np.fft.rfft(windowed_values)
    frequency = np.fft.rfftfreq(fft_count, d=spacing)
    magnitude = np.abs(spectrum)
    frequency_range = (0.0, float(frequency[-1])) if frequency.size else (0.0, 0.0)
    return SpectrumData(
        name=name,
        frequency=frequency,
        magnitude=magnitude,
        source_channel=channel.name,
        color=channel.color,
        time_range=(float(selected_time[0]), float(selected_time[-1])),
        frequency_range=frequency_range,
        window_id=window_id,
        remove_dc=remove_dc,
        zero_pad=zero_pad,
        sample_count=sample_count,
        fft_count=fft_count,
    )


def window_values(window_id: str, count: int) -> np.ndarray:
    if count < 0:
        raise ValueError("Window sample count cannot be negative")
    function = WINDOW_FUNCTION_BY_ID.get(window_id)
    if function is None:
        raise ValueError(f"Unknown FFT window: {window_id}")
    return np.asarray(function.evaluator(count), dtype=float)


def zero_padded_length(sample_count: int, zero_pad: str) -> int:
    if sample_count < 1:
        raise ValueError("FFT requires at least one sample")
    if zero_pad == "none":
        return sample_count
    if zero_pad == "next_pow2":
        return 1 << (sample_count - 1).bit_length()
    if zero_pad.endswith("x"):
        multiplier = int(zero_pad[:-1])
        if multiplier < 1:
            raise ValueError("Zero padding multiplier must be at least 1")
        return sample_count * multiplier
    raise ValueError(f"Unknown zero padding option: {zero_pad}")


def filtered_spectrum(spectrum: SpectrumData, frequency_range: tuple[float, float]) -> tuple[np.ndarray, np.ndarray]:
    low, high = sorted(frequency_range)
    mask = (spectrum.frequency >= low) & (spectrum.frequency <= high)
    return spectrum.frequency[mask], spectrum.magnitude[mask]


def default_result_name(function_id: str, operand_a: str, operand_b: str | None = None) -> str:
    label = MATH_FUNCTION_BY_ID[function_id].label
    result = label.replace("A", operand_a)
    if operand_b is not None:
        result = result.replace("B", operand_b)
    return result


def _derived_unit(function_id: str, operand_a: ChannelData, operand_b: ChannelData | None) -> str | None:
    unit_a = operand_a.unit or None
    unit_b = operand_b.unit if operand_b is not None else None
    if function_id in {"abs", "negate"}:
        return unit_a
    if function_id == "square":
        return _power_unit(unit_a, 2)
    if function_id == "sqrt":
        return f"sqrt({unit_a})" if unit_a else None
    if function_id in {"log10", "ln"}:
        return None
    if function_id in {"add", "subtract"} and operand_b is not None and unit_a == unit_b:
        return unit_a
    if function_id == "multiply" and operand_b is not None:
        if unit_a and unit_b:
            return _power_unit(unit_a, 2) if unit_a == unit_b else f"{unit_a}*{unit_b}"
        return unit_a or unit_b
    if function_id == "divide" and operand_b is not None:
        if unit_a and unit_b:
            return None if unit_a == unit_b else f"{unit_a}/{unit_b}"
        if unit_a:
            return unit_a
        if unit_b:
            return f"1/{unit_b}"
    return None


def _power_unit(unit: str | None, exponent: int) -> str | None:
    return f"{unit}^{exponent}" if unit else None
