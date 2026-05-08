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
- Main waveform plot with X pan/zoom and active-axis Y pan/zoom.
- Preview window with the same left/right Y scaling as the main plot.
- Preview highlight region controls the main X range after mouse release.
- Movable X and Y cursors with position, delta, and active-channel interpolated values.
- Cursor axis group selector, with active-channel choices filtered to the cursor group.
- Reset Cursors button to move cursors to the active Y group and current screen center.

## Shortcuts And Controls

| Action | Control |
| --- | --- |
| Open CSV | `Ctrl+O` / `Cmd+O` |
| Toggle active Y control group | `T` |
| Pan X | drag on main plot |
| Pan active Y axis | `Ctrl` + drag on main plot |
| Zoom X | mouse wheel on main plot |
| Zoom active Y axis | `Ctrl` + mouse wheel on main plot |
| Toolbar zoom | choose `X` or `Y`, then use `Zoom In` / `Zoom Out` |
| Reset view | `Reset View` toolbar button |
| Configure waveform axis groups | `Axis Groups` toolbar button |
| Enable cursors | `X cursors` / `Y cursors` checkboxes |
| Reset cursors | `Reset Cursors` button in the Cursors tab |

When `Y` is selected in the toolbar zoom control, zoom buttons apply to the currently active Y control group. Press `T` to switch that active group between left and right. Cursor axis group is controlled separately in the Cursors tab, so switching active Y control does not move existing cursors.
