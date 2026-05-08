# CSV Waveform Viewer

A Python desktop waveform viewer for numeric CSV files, built with PySide6 and pyqtgraph.

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

The app detects a time-like column such as `TimeOutput`, filters out mostly invalid channels, and plots valid channels with oscilloscope-style colors. Use the channel checkboxes to control visible traces, the mouse wheel and drag gestures to navigate, the lower preview region to select a time span, and the cursor tab to enable movable X/Y cursors.

## Major Features

- CSV loading with automatic time-base detection and numeric channel filtering.
- Oscilloscope-style channel colors.
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
- Movable dashed X and Y cursors with on-plot labels, position, delta, and active-channel interpolated values.
- Cursor labels can be dragged directly to move the corresponding cursor.
- Cursor axis group selector, with active-channel choices filtered to the cursor group.
- Grouped cursor readouts for X positions, Y positions, and active-channel values.
- Reset Cursors button/shortcut to move cursors to the active Y group and current screen center.

## Shortcuts And Controls

| Action | Control |
| --- | --- |
| Open CSV | `Ctrl+O` / `Cmd+O` |
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
