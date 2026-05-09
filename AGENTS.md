# Agent Brief

## Project

CSV Waveform Viewer is a PySide6/pyqtgraph desktop app for plotting numeric CSV/Excel waveform data with configurable time bases, dual Y axes, preview-range navigation, trace highlighting, cursor measurements, calculated traces, and FFT spectrum analysis.

Entry point:

```bash
python main.py example_csv/1t1r_set_read_0P1V.csv
```

Tests:

```bash
.\.venv\Scripts\python.exe -m pytest
```

## Important Environment Notes

- The active Windows virtualenv has Python 3.12.
- Import order matters with current `PySide6`/`pandas`/`six` on Python 3.12:
  - Import `csv_loader`/`pandas` before `PySide6` where practical.
  - `main.py`, `viewer.py`, and `plot_widgets.py` intentionally preserve this order.
- Excel loading uses `xlrd` for `.xls` and `openpyxl` for `.xlsx`/`.xlsm`.
- Old `.xls` files may emit `xlrd` OLE2 consistency warnings; `csv_loader.py` intentionally quiets stdout/stderr while pandas inspects/reads Excel files.
- Git may require `-c safe.directory=C:/Users/barry/Documents/cswave` because the sandbox user differs from the repo owner.
- OpenGL is optional:
  - Startup default can be set with `CSWAVE_OPENGL=1`.
  - Display menu renderer selector can switch CPU/OpenGL at runtime.
  - Renderer switching intentionally rebuilds curves to avoid stale pyqtgraph/OpenGL render caches.

## File Map

- `main.py`: argparse entry point and QApplication startup.
- `csv_loader.py`: CSV/Excel parsing, sheet discovery, time-column detection, numeric filtering, channel/timebase metadata.
- `math_engine.py`: unary/binary math registry, FFT/window/zero-padding helpers, `SpectrumData`.
- `viewer.py`: main window, native menu bar, side tabs, channel controls, cursor readout panel, Math tab, Waveform Setup dialog.
- `plot_widgets.py`: waveform plotting engine, spectrum plotting engine, dual axes, preview region, cursor items, renderer switching, interaction behavior.
- `tests/test_csv_loader.py`: CSV/Excel loader and import-order regression tests.
- `tests/test_math_engine.py`: calculated trace, FFT, windowing, DC removal, and zero-padding tests.
- `tests/test_plot_widgets.py`: plot widget behavior regressions.
- `tests/test_viewer_math.py`: viewer-level Math, Spectrum, Excel sheet selection, and setup workflow tests.

## Code Framework

Use this section to avoid rereading the whole repo for common changes.

### Data Flow

1. `main.py` creates `QApplication`, constructs `MainWindow`, and optionally calls `window.load_file(..., show_setup=True)`.
2. `viewer.MainWindow.load_file()` calls `csv_loader.load_waveform()`, stores the original loaded data in `self.source_data`, clears session math outputs, and calls `WaveformPlot.set_data()`.
3. `csv_loader.WaveformData` is the shared source shape:
   - `time`: current X-axis values.
   - `channels`: currently plot-eligible signals, excluding the active time column.
   - `time_candidates`: all valid numeric columns that can become signals or timebase candidates.
   - `timebase_kind`, `timebase_value`, `time_column`: current timebase metadata.
4. `viewer._waveform_with_timebase()` rebuilds `WaveformData` when Waveform Setup changes the timebase.
5. `plot_widgets.WaveformPlot` owns waveform rendering, channel selection, axis settings, cursor placement/readout, preview synchronization, highlighting, and renderer switching.
6. `math_engine.py` is pure calculation code. It should not import Qt or pyqtgraph.
7. `plot_widgets.SpectrumPlot` owns display and interaction for the active `SpectrumData`.

### Main State Owners

- Loaded source waveform: `MainWindow.source_data`.
- Current displayed waveform plus session math channels: `MainWindow.data`.
- Session-only calculated time traces: `MainWindow.calculated_channels`.
- Session-only FFT spectra: `MainWindow.spectra`.
- Axis grouping/ranges: `WaveformPlot.axis_settings`.
- Visible channels: `WaveformPlot.selected_channels`.
- Active/focused trace: `WaveformPlot.focused_channel`.
- Cursor values and interpolation: `WaveformPlot.cursor_values()`.
- Math function/window/zero-padding registries: `math_engine.py`.

### Common Change Points

- Add or change file loading: start in `csv_loader.load_waveform()` and `_waveform_from_frame()`, then add tests in `tests/test_csv_loader.py`.
- Change timebase behavior: start in `viewer._waveform_with_timebase()`, `AxisSetupDialog`, and `tests/test_viewer_math.py`.
- Change axis setup UI: use `AxisSetupDialog`; apply changes through `MainWindow._open_waveform_setup()`.
- Change waveform plot interaction/rendering: use `WaveformPlot` and `WaveformViewBox` in `plot_widgets.py`; add focused tests in `tests/test_plot_widgets.py`.
- Change preview behavior: use `WaveformPlot._on_x_range_changed()`, `_set_preview_range_for_region()`, `_zoom_preview_from_wheel()`, and related tests.
- Add time-domain math: update `math_engine.MATH_FUNCTIONS`, `create_calculated_channel()`, and tests in `tests/test_math_engine.py`.
- Change FFT behavior: update `math_engine.create_fft_spectrum()` and `SpectrumData`; preserve the order clip -> DC removal -> window -> zero pad -> `rfft`.
- Change Math tab UI behavior: use `MainWindow._build_math_panel()` and the `_add_*`, `_update_*`, `_math_output_selected()` methods.
- Change spectrum interaction/display: use `SpectrumPlot` and `SpectrumViewBox`; avoid touching waveform view code unless behavior must be shared.
- Change menu shortcuts/actions: use `MainWindow._build_actions()` and `_build_shortcuts()`.

### Read Sparingly

- Do not reread all of `plot_widgets.py` for loader, math-engine, or README-only changes.
- Do not reread all of `viewer.py` when only changing pure math; inspect the specific Math tab method that calls the engine.
- Do not inspect renderer/OpenGL code unless changing renderer mode, curve rebuilding, or performance behavior.
- Do not inspect cursor label internals unless changing cursor drag/label behavior.
- For most changes, inspect the relevant method plus nearby tests first, then expand only if the call path is unclear.

## Loading And Setup

- `Open Waveform` supports `.csv`, `.xls`, `.xlsx`, and `.xlsm`.
- Excel files with multiple sheets prompt the user to choose the sheet containing waveforms.
- Loading through `File` > `Open Waveform` or a startup argument opens `Waveform Setup` automatically (`show_setup=True`); programmatic/test `load_file()` calls are non-modal by default.
- `Waveform Setup` controls both X-axis timebase and Y-axis grouping:
  - `Time column`: selected numeric column must be finite, strictly increasing, and uniformly spaced; selected column is removed from plotted signals.
  - `Sample rate (Sa/s)`: generated time is `sample_index / sample_rate`; all numeric columns, including detected time, are normal signals.
  - `Sample interval (s/pt)`: generated time is `sample_index * sample_interval`; all numeric columns are normal signals.
  - `Sample index`: generated `0, 1, 2, ...`; all numeric columns are normal signals.
- If a detected time column is overridden with a generated timebase, treat that detected time column as a regular signal.
- Applying a different timebase rebuilds source waveform data and clears session-only calculated traces/spectra.

## Interaction Model

- Main plot:
  - Wheel zooms X.
  - Ctrl/Cmd + wheel zooms active Y group.
  - Drag pans X.
  - Ctrl/Cmd + drag pans active Y group.
  - Clicking a waveform highlights it, dims other traces, and switches active Y group.
  - While a waveform is highlighted, drag free-pans X plus that waveform's Y group.
  - Clicking empty plot space clears waveform highlight.
- Preview bar:
  - Highlighted region controls main X range after release.
  - Wheel zooms preview X while preserving the highlighted region's visual footprint and updating the main X range.
  - Right preview axis mouse interaction is disabled so it cannot free-zoom Y.
- Cursors:
  - X/Y cursors are dashed, labeled, and movable by dragging either the line or label.
  - Cursor axis group is independent of active Y control group.
- Spectrum view:
  - Wheel zooms frequency.
  - Ctrl/Cmd + wheel zooms magnitude.
  - Drag pans frequency.
  - Ctrl/Cmd + drag pans magnitude.
  - Frequency and magnitude are clamped at zero.
  - Hover near a spectral peak to show frequency and energy.
- Math outputs:
  - Clicking a calculated waveform output switches to `Waveforms` and highlights the trace.
  - Clicking an FFT output switches to `Spectrum`.

## Math And FFT

- Math tab outputs are session-only and cleared on new waveform load or timebase changes.
- Time-domain functions become first-class waveform channels and participate in channel checkboxes, axis setup, preview, legend, highlighting, and cursor readouts.
- Supported unary functions: `A^2`, `sqrt(A)`, `abs(A)`, `log10(A)`, `ln(A)`, `-A`.
- Supported binary functions: `A+B`, `A-B`, `A*B`, `A/B`.
- Operand dropdowns have `Pick` buttons: click `Pick`, then click a waveform trace to fill operand A/B while preserving normal trace highlighting.
- `FFT(A)` creates a frequency-domain `SpectrumData`:
  - Uses full finite waveform time range when X cursors are hidden.
  - Uses sorted `X1`/`X2` interval when X cursors are visible.
  - `Update FFT` recomputes using current X cursors, window, DC, and zero-padding settings.
  - Window choices: `Rectangular`, `Hann`, `Hamming`, `Cosine`.
  - `Remove DC offset` subtracts the selected segment mean before windowing.
  - `Zero pad`: `None`, `Next power of 2`, `2x`, `4x`, `8x`; denser bins only, not true frequency resolution.
  - Spectrum line color matches the source waveform.
  - Frequency min/max filters display without recomputing FFT.

## Menu Bar

The native Qt menu bar is organized as:

- File: `Open Waveform`
- View: `Reset View`, `Waveform Setup...`
- Navigate: `Y group`, `Zoom` axis selection, `Zoom In`, `Zoom Out`
- Display: `Renderer` (`CPU` / `OpenGL`), `Language`, `Force dark`

Shortcuts:

- `Ctrl+O` / `Cmd+O`: open waveform
- `T`: toggle active Y group
- `Ctrl+R` / `Cmd+R`: reset the active plot tab (`Waveforms` or `Spectrum`)
- `Shift+R`: reset cursors
- `X`: toggle X cursors
- `Y`: toggle Y cursors

## Performance Notes

- `PlotDataItem` curves use `clipToView`, auto downsampling, and skip finite checks.
- During interaction, main curves temporarily use `subsample` downsampling, then restore to `peak`.
- Preview curves always use `subsample`.
- Preview range updates are throttled during main plot movement.
- FFT zero padding increases bin density and memory/compute cost proportional to selected padded FFT length.
- Remaining heavy cost is mostly Qt/pyqtgraph painting, not Python-side data loading.
- Future robust optimization path: precomputed min/max LOD pyramid per trace.

## Common Gotchas

- Avoid replacing the preview's default `ViewBox` unless you also preserve region synchronization; an earlier custom preview viewbox broke highlighted-region behavior.
- Custom `ViewBox.wheelEvent` overrides must accept pyqtgraph's optional `axis` keyword/argument; axis-wheel interaction calls `wheelEvent(event, axis=1)`.
- If changing renderer mode or OpenGL behavior, verify CPU -> OpenGL -> CPU switching with loaded data.
- If moving curves between left/right groups, Y ranges must be recalculated for affected Waveform Setup groups and applied to both main and preview viewboxes.
- If changing timebase behavior, preserve the invariant that selected time columns are not plotted, generated timebases make all valid numeric columns plot-eligible, and math outputs/spectra clear after source timebase changes.
- If changing cursor labels, preserve drag behavior via `CursorLineLabel`.
- If changing focus/highlight behavior, preserve z-order:
  - zero lines stay behind traces,
  - focused trace draws above other traces,
  - right-axis viewbox lifts only when right-axis trace is focused.
- If changing FFT behavior, keep the order: clip by X cursor range, remove DC if enabled, apply window, then zero-pad before `rfft`.
