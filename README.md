# CSV Waveform Viewer

A Python desktop waveform viewer for CSV and xls files, built with codex, PySide6 and pyqtgraph. There may be undiscovered bugs so feel free to leave issue cards on GitHub!

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python main.py example_csv/1t1r_set_read_0P1V.csv
```

The app loads CSV and Excel waveform files, detects a time-like column such as `TimeOutput`, filters out mostly invalid channels, and plots valid channels with oscilloscope-style colors. Use the channel checkboxes to control visible traces, the mouse wheel and drag gestures to navigate, the lower preview region to select a time span, and the cursor tab to enable movable X/Y cursors.

## Major Features

- CSV/XLS/XLSX loading with automatic time-base detection and numeric channel filtering.
- Sheet selection for Excel files with multiple sheets.
- Oscilloscope-style visuals.
- Dual Y axes with independent left/right Y ranges.
- Automatic default grouping:
  - voltage channels (`V`) on the left axis
  - current channels (`A`) on the right axis
  - non-V/I channels disabled by default
- Axis Groups dialog for assigning waveforms to left, right, or disabled groups, plus units and initial Y ranges.
- Channel selector for showing or hiding enabled waveforms.
- Toolbar controls for active Y axis group, zoom axis, and renderer selection.
- Main waveform plot with X pan/zoom and active-axis Y pan/zoom.
- Click a waveform to highlight it, dim other traces, and switch to that waveform's axis group.
- Highlighted waveform mode supports free X/Y panning for the active trace group.
- Preview window with the same left/right Y scaling as the main plot.
- Preview highlight region controls the main X range after mouse release.
- Mouse wheel on the preview zooms the preview time scale while preserving the highlighted region's visual footprint.
- Optional OpenGL renderer, selectable from the toolbar or at startup with `CSWAVE_OPENGL=1`.
- Movable X and Y cursors with on-plot labels, position, delta, and active-channel interpolated values.
- Cursor labels can be dragged directly to move the corresponding cursor.
- Cursor axis group selector, with active-channel choices filtered to the cursor group.
- Grouped cursor readouts for X positions, Y positions, and active-channel values.
- Reset Cursors button/shortcut to move cursors to the active Y group and current screen center.
- Math tab for calculated traces and FFT spectrum analysis.

## Shortcuts And Controls

| Action | Control |
| --- | --- |
| Open waveform | `Ctrl+O` / `Cmd+O` |
| Toggle active Y control group | `T` |
| Select active Y control group | `Y group` toolbar dropdown |
| Pan X | drag on main plot |
| Pan active Y axis | `Ctrl` + drag on main plot |
| Free-pan highlighted trace | click a waveform, then drag on main plot |
| Zoom X | mouse wheel on main plot |
| Zoom active Y axis | `Ctrl` + mouse wheel on main plot |
| Preview time zoom | mouse wheel on preview bar |
| Preview range selection | drag/release the highlighted preview region |
| Highlight waveform | left-click a visible waveform |
| Clear waveform highlight | left-click empty plot space |
| Toolbar zoom | choose `X` or `Y`, then use `+` / `-` |
| Reset view | `Ctrl+R` / `Cmd+R` or `Reset View` toolbar button |
| Configure waveform axis groups | `Axis Groups...` toolbar button |
| Select renderer | `Renderer` toolbar dropdown (`CPU` / `OpenGL`) |
| Toggle X cursors | `X` or `X cursors` checkbox |
| Toggle Y cursors | `Y` or `Y cursors` checkbox |
| Move cursor | drag the dashed cursor line or its label |
| Reset cursors | `Shift+R` or `Reset Cursors` button in the Cursors tab |

When `Y` is selected in the toolbar zoom control, zoom buttons apply to the currently active Y control group. Press `T` or use the `Y group` dropdown to switch that active group between left and right. Cursor axis group is controlled separately in the Cursors tab, so switching active Y control does not move existing cursors.

## Math

The Math tab creates session-only calculated outputs from loaded waveforms. Loading a new waveform file clears calculated traces and spectra.

### Time-Domain Traces

Choose a function, select operand `A` and, for binary functions, operand `B`, then enter or accept the generated output name and press `Add`. You can also press `Pick` next to an operand and then click a waveform trace in the main plot to fill that operand. Time-domain results are added as normal waveform traces, so they appear in the channel list, legend, preview, axis setup, trace highlighting, and cursor readouts.

Supported time-domain functions:

| Type | Functions |
| --- | --- |
| Unary | `A^2`, `sqrt(A)`, `abs(A)`, `log10(A)`, `ln(A)`, `-A` |
| Binary | `A+B`, `A-B`, `A*B`, `A/B` |

Invalid numerical results, such as divide-by-zero or square root of a negative value, are left as non-finite samples and skipped by the plot.

### FFT Spectrum

Select `FFT(A)` to create a frequency-domain spectrum from waveform `A`. The spectrum opens in the `Spectrum` view, uses the source waveform color, and plots linear magnitude versus frequency in Hz.

FFT controls:

| Control | Behavior |
| --- | --- |
| `Window` | Applies `Rectangular`, `Hann`, `Hamming`, or `Cosine` windowing before the FFT. |
| `Remove DC offset` | Subtracts the selected segment mean before windowing so the DC bin does not dominate the Y range. |
| `Zero pad` | Adds zeros after the selected segment for denser FFT bins. Options are `None`, `Next power of 2`, `2x`, `4x`, and `8x`. This improves display/interpolation density, not true frequency resolution. |
| `Add` | Creates or replaces the named FFT spectrum. |
| `Update FFT` | Recalculates the selected spectrum using the current X cursor range, window, DC, and zero-padding settings. |
| `Min Hz` / `Max Hz` | Filters the displayed frequency range without recomputing the FFT. |

FFT time range:

- If X cursors are hidden, FFT uses the full finite waveform time range.
- If X cursors are visible, FFT uses the sorted interval between `X1` and `X2`.
- Moving the X cursors does not automatically recompute the spectrum; press `Update FFT`.

Spectrum view:

- Wheel zooms frequency.
- `Ctrl`/`Cmd` + wheel zooms magnitude.
- Drag pans frequency.
- `Ctrl`/`Cmd` + drag pans magnitude.
- Frequency and magnitude are clamped at zero.
- Hover near a spectral peak to show frequency and energy.

Clicking an item in the Math output list switches to its corresponding view. Calculated waveform outputs switch to `Waveforms` and highlight the trace; FFT outputs switch to `Spectrum`.