# CSV Waveform Viewer

A Python desktop waveform viewer for CSV and xls files, built with codex, PySide6 and pyqtgraph. This app is tested on modern versions of OSX, Ubuntu, and Windows. There may be undiscovered bugs so feel free to leave issue cards on GitHub!

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

## Demo

| Waveform viewer | FFT spectrum |
| --- | --- |
| ![Waveform viewer with native menus and dark oscilloscope-style plots](demo_pics/Look.png) | ![FFT spectrum view with math controls](demo_pics/FFT.png) |

| Localization and detached panels | Ubuntu/system look |
| --- | --- |
| ![Localized UI with a detached right-side panel](demo_pics/MultiLang_Detach.png) | ![CSV Waveform Viewer running on Ubuntu](demo_pics/Ubuntu.png) |

## Download And Run

Packaged releases are intended for users who do not want to install Python.

| Platform | How to run |
| --- | --- |
| Windows | Download `cswave-<version>-windows-x64.zip`, unzip it, and run `cswave.exe`. |
| macOS | Download `cswave-<version>-macos.zip`, unzip it, and open `CSV Waveform Viewer.app`. If macOS blocks the first launch, use Finder > Open from the context menu. |
| Linux | Download `cswave-<version>-linux-x64.tar.gz`, extract it, and run `cswave/cswave`. |

You can open files from `File` > `Open Waveform`, so command-line usage is optional.

## Major Features

- CSV/XLS/XLSX loading with automatic time-base detection and numeric channel filtering.
- Sheet selection for Excel files with multiple sheets.
- Oscilloscope-style visuals.
- Dual Y axes with independent left/right Y ranges.
- Automatic default grouping:
  - voltage channels (`V`) on the left axis
  - current channels (`A`) on the right axis
  - non-V/I channels disabled by default
- Waveform Setup dialog for selecting/overriding the time base and assigning waveforms to left, right, or disabled groups.
- Channel selector for showing or hiding enabled waveforms.
- Native menu controls for opening waveforms, active Y axis group, zoom, renderer selection, theme, and language.
- Main waveform plot with X pan/zoom and active-axis Y pan/zoom.
- Click a waveform to highlight it, dim other traces, and switch to that waveform's axis group.
- Highlighted waveform mode supports free X/Y panning for the active trace group.
- Preview window with the same left/right Y scaling as the main plot.
- Preview highlight region controls the main X range after mouse release.
- Mouse wheel on the preview zooms the preview time scale while preserving the highlighted region's visual footprint.
- Optional OpenGL renderer, selectable from the Display menu or at startup with `CSWAVE_OPENGL=1`.
- Movable X and Y cursors with on-plot labels, position, delta, and active-channel interpolated values.
- Cursor labels can be dragged directly to move the corresponding cursor.
- Cursor axis group selector, with active-channel choices filtered to the cursor group.
- Grouped cursor readouts for X positions, Y positions, and active-channel values.
- Reset Cursors button/shortcut to move cursors to the active Y group and current screen center.
- Math tab for calculated traces and FFT spectrum analysis.

## Shortcuts And Controls

| Action | Control |
| --- | --- |
| Open waveform | `Ctrl+O` / `Cmd+O` or `File` > `Open Waveform` |
| Toggle active Y control group | `T` |
| Select active Y control group | `Navigate` > `Y group` |
| Pan X | drag on main plot |
| Pan active Y axis | `Ctrl` + drag on main plot |
| Free-pan highlighted trace | click a waveform, then drag on main plot |
| Zoom X | mouse wheel on main plot |
| Zoom active Y axis | `Ctrl` + mouse wheel on main plot |
| Preview time zoom | mouse wheel on preview bar |
| Preview range selection | drag/release the highlighted preview region |
| Highlight waveform | left-click a visible waveform |
| Clear waveform highlight | left-click empty plot space |
| Menu zoom | choose `Navigate` > `Zoom` > `X` or `Y`, then use `Zoom In` / `Zoom Out` |
| Reset view | `Ctrl+R` / `Cmd+R` or `View` > `Reset View` |
| Configure waveform setup | `View` > `Waveform Setup...` |
| Select renderer | `Display` > `Renderer` (`CPU` / `OpenGL`) |
| Toggle X cursors | `X` or `X cursors` checkbox |
| Toggle Y cursors | `Y` or `Y cursors` checkbox |
| Move cursor | drag the dashed cursor line or its label |
| Reset cursors | `Shift+R` or `Reset Cursors` button in the Cursors tab |

When `Y` is selected in the Navigate zoom control, zoom commands apply to the currently active Y control group. Press `T` or use the `Y group` menu control to switch that active group between left and right. Cursor axis group is controlled separately in the Cursors tab, so switching active Y control does not move existing cursors.

## Waveform Setup

Waveform Setup opens after loading a waveform file and is also available from the View menu. It controls the X-axis time base and each waveform's Y-axis assignment.

Time-base options:

| Mode | Behavior |
| --- | --- |
| `Time column` | Uses a selected numeric column as the X axis. The column must be finite and strictly increasing. Nonuniform spacing is allowed with a warning; FFT uses median spacing. The selected time column is not plotted as a signal. |
| `Sample rate (Sa/s)` | Generates time as `sample_index / sample_rate`. All valid numeric columns, including any detected time column, are treated as normal signals. |
| `Sample interval (s/pt)` | Generates time as `sample_index * sample_interval`. All valid numeric columns, including any detected time column, are treated as normal signals. |
| `Sample index` | Uses `0, 1, 2, ...` as the X axis. All valid numeric columns are treated as normal signals. |

If a file has a detected time column, you can still override it with a generated time base. In that case, the detected time column becomes a normal signal that can be assigned to an axis or disabled like any other waveform.

The waveform table assigns each signal to the left axis, right axis, or disabled state, and lets you edit axis units and initial Y ranges.

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

Select `FFT(A)` to create a frequency-domain spectrum from waveform `A`. The spectrum opens in the `Spectrum` view, uses the source waveform color, and plots magnitude in dB versus frequency in Hz.

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
- Frequency is clamped to the displayed spectrum range.
- Hover near a spectral peak to show frequency and magnitude in dB.

Clicking an item in the Math output list switches to its corresponding view. Calculated waveform outputs switch to `Waveforms` and highlight the trace; FFT outputs switch to `Spectrum`.

## Localization

The GUI uses Qt-native translation support. English is the source language and fallback.

By default, the app uses the operating system language when a matching compiled translation exists. You can also pass an explicit startup locale:

```bash
python main.py --language zh_CN example_csv/1t1r_set_read_0P1V.csv
```

Use `--language system` to explicitly request the system language.

The `Display` menu also has a `Language` selector. Choosing a different language prompts for a restart and relaunches the app with the selected startup locale.

Translation files live in `translations/`:

- `cswave_en.ts` is the English reference catalog.
- `cswave_zh_CN.ts` / `.qm` and `cswave_ja_JP.ts` / `.qm` provide Chinese and Japanese translations.
- Translators can create additional `cswave_<locale>.ts` files.
- Compiled runtime files are named `cswave_<locale>.qm`.

Typical translator workflow:

```bash
pyside6-lupdate main.py viewer.py plot_widgets.py -ts translations/cswave_en.ts
pyside6-lupdate main.py viewer.py plot_widgets.py -ts translations/cswave_zh_CN.ts
pyside6-lrelease translations/cswave_zh_CN.ts -qm translations/cswave_zh_CN.qm
```

## Building Releases

Release builds use PyInstaller and include translations, examples, README, and license files. Build artifacts are written to `release/`.

Windows:

```powershell
.\scripts\build_windows.ps1
```

macOS:

```bash
./scripts/build_macos.sh
```

Linux:

```bash
./scripts/build_linux.sh
```

Set `SKIP_TESTS=1` on macOS/Linux or pass `-SkipTests` on Windows to skip the test run during packaging.

## License

CSV Waveform Viewer is released under the MIT License. See [LICENSE](LICENSE).
