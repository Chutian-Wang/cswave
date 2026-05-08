# Agent Brief

## Project

CSV Waveform Viewer is a PySide6/pyqtgraph desktop app for plotting numeric CSV waveform data with dual Y axes, preview-range navigation, trace highlighting, and cursor measurements.

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
- Git may require `-c safe.directory=C:/Users/barry/Documents/cswave` because the sandbox user differs from the repo owner.
- OpenGL is optional:
  - Startup default can be set with `CSWAVE_OPENGL=1`.
  - Toolbar renderer selector can switch CPU/OpenGL at runtime.
  - Renderer switching intentionally rebuilds curves to avoid stale pyqtgraph/OpenGL render caches.

## File Map

- `main.py`: argparse entry point and QApplication startup.
- `csv_loader.py`: CSV parsing, time-column detection, numeric filtering, channel metadata.
- `viewer.py`: main window, toolbar, side tabs, channel controls, cursor readout panel, axis setup dialog.
- `plot_widgets.py`: plotting engine, dual axes, preview region, cursor items, renderer switching, interaction behavior.
- `tests/test_csv_loader.py`: CSV loader and import-order regression tests.
- `tests/test_plot_widgets.py`: plot widget behavior regressions.

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

## Toolbar

Toolbar is organized as:

- File: `Open CSV`
- View: `Reset View`, `Axis Groups...`
- Navigate: `Y group`, `Zoom`, `+`, `-`
- Display: `Renderer` (`CPU` / `OpenGL`)

Shortcuts:

- `Ctrl+O` / `Cmd+O`: open CSV
- `T`: toggle active Y group
- `Ctrl+R` / `Cmd+R`: reset view
- `Shift+R`: reset cursors
- `X`: toggle X cursors
- `Y`: toggle Y cursors

## Performance Notes

- `PlotDataItem` curves use `clipToView`, auto downsampling, and skip finite checks.
- During interaction, main curves temporarily use `subsample` downsampling, then restore to `peak`.
- Preview curves always use `subsample`.
- Preview range updates are throttled during main plot movement.
- Remaining heavy cost is mostly Qt/pyqtgraph painting, not Python-side data loading.
- Future robust optimization path: precomputed min/max LOD pyramid per trace.

## Common Gotchas

- Avoid replacing the preview's default `ViewBox` unless you also preserve region synchronization; an earlier custom preview viewbox broke highlighted-region behavior.
- If changing renderer mode or OpenGL behavior, verify CPU -> OpenGL -> CPU switching with loaded data.
- If moving curves between left/right groups, Y ranges must be recalculated for affected axis groups and applied to both main and preview viewboxes.
- If changing cursor labels, preserve drag behavior via `CursorLineLabel`.
- If changing focus/highlight behavior, preserve z-order:
  - zero lines stay behind traces,
  - focused trace draws above other traces,
  - right-axis viewbox lifts only when right-axis trace is focused.
