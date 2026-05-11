# CSV Waveform Viewer

[English](README.md) | [日本語](README.ja_JP.md)

CSV Waveform Viewer 是一个用于 CSV 和 Excel 波形文件的 Python 桌面查看器，基于 PySide6 和 pyqtgraph 构建。该应用已在现代版本的 macOS、Ubuntu 和 Windows 上测试。仍可能存在未知问题，欢迎在 GitHub 上提交 issue。

代码仓库：<https://github.com/Chutian-Wang/cswave.git>

## 安装开发环境

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 运行源码版本

```bash
python main.py example_csv/1t1r_set_read_0P1V.csv
```

应用可以加载 CSV 和 Excel 波形文件，自动检测类似 `TimeOutput` 的时间列，过滤掉大部分无效通道，并用示波器风格的颜色绘制有效通道。你可以用通道复选框控制可见波形，用鼠标滚轮和拖拽进行导航，用底部预览区域选择时间范围，并在游标页启用可移动的 X/Y 游标。

## 演示

| 波形查看器 | FFT 频谱 |
| --- | --- |
| ![带原生菜单和深色示波器风格绘图的波形查看器](demo_pics/Look.png) | ![带数学控件的 FFT 频谱视图](demo_pics/FFT.png) |

| 本地化和可分离面板 | Ubuntu/系统外观 |
| --- | --- |
| ![本地化界面和分离的右侧面板](demo_pics/MultiLang_Detach.png) | ![在 Ubuntu 上运行的 CSV Waveform Viewer](demo_pics/Ubuntu.png) |

## 下载和运行

打包版本面向不想安装 Python 的用户。

| 平台 | 运行方式 |
| --- | --- |
| Windows | 下载 `cswave-<version>-windows-x64.zip`，解压后运行 `cswave.exe`。 |
| macOS | 下载 `cswave-<version>-macos.zip`，解压后打开 `CSV Waveform Viewer.app`。如果 macOS 首次启动时拦截应用，请在 Finder 中右键选择“打开”。 |
| Linux | 下载 `cswave-<version>-linux-x64.tar.gz`，解压后运行 `cswave/cswave`。 |

可以通过 `File` > `Open Waveform` 打开文件，也可以把支持的波形文件拖放到应用窗口中，因此不需要使用命令行。

## 主要功能

- CSV/XLS/XLSX 加载，自动检测时间基准并过滤数字通道。
- 支持拖放打开 `.csv`、`.xls`、`.xlsx` 和 `.xlsm` 波形文件。
- Excel 多工作表文件的工作表选择。
- 示波器风格显示。
- 双 Y 轴，左右 Y 范围独立。
- 自动默认分组：
  - 电压通道（`V`）放在左轴
  - 电流通道（`A`）放在右轴
  - 非 V/I 通道默认禁用
- Waveform Setup 对话框可选择/覆盖时间基准，并把波形分配到左轴、右轴或禁用组。
- Channels 页可显示/隐藏启用的波形，并可拖拽通道到左轴、右轴或禁用组。
- 原生菜单用于打开波形、选择活动 Y 轴组、缩放、选择渲染器、外观和语言。
- 主波形图支持 X 平移/缩放和活动 Y 轴平移/缩放。
- 点击波形可高亮该波形、淡化其他曲线，并切换到该波形所在轴组。
- 高亮波形模式支持对活动曲线组进行自由 X/Y 平移。
- 预览窗口使用与主图相同的左右 Y 轴缩放。
- 释放预览高亮区域后可控制主图 X 范围。
- 在预览区域使用鼠标滚轮可缩放预览时间尺度，同时保持高亮区域的视觉宽度。
- 可选 OpenGL 渲染器，可从 Display 菜单选择，也可启动前设置 `CSWAVE_OPENGL=1`。
- 可移动 X/Y 游标，带图上标签、位置、差值、活动通道插值读数、单位和 SI 缩放选择。
- 游标标签可直接拖拽。
- 游标轴组选择器会按游标组过滤活动通道。
- 游标读数按 X 位置、Y 位置和活动通道值分组显示。
- Reset Cursors 按钮/快捷键可把游标移动到活动 Y 轴组和当前屏幕中心。
- Math 页支持计算波形和 FFT 频谱分析。
- Measure 页支持多信号纵向和频率读数卡片，包含单位、SI 缩放选择、游标范围测量，以及每个信号独立分离到浮动窗口的能力。

## 快捷键和控制

| 操作 | 控制 |
| --- | --- |
| 打开波形 | `Ctrl+O` / `Cmd+O`、`File` > `Open Waveform`，或把波形文件拖放到应用中 |
| 切换活动 Y 控制组 | `T` |
| 选择活动 Y 控制组 | `Navigate` > `Y group` |
| 平移 X | 在主图拖拽 |
| 平移活动 Y 轴 | `Ctrl` + 在主图拖拽 |
| 自由平移高亮曲线 | 点击波形后在主图拖拽 |
| 缩放 X | 在主图使用鼠标滚轮 |
| 缩放活动 Y 轴 | `Ctrl` + 鼠标滚轮 |
| 预览时间缩放 | 在预览条使用鼠标滚轮 |
| 预览范围选择 | 拖拽/释放预览高亮区域 |
| 高亮波形 | 左键点击可见波形 |
| 清除高亮 | 左键点击图中空白处 |
| 菜单缩放 | 选择 `Navigate` > `Zoom` > `X` 或 `Y`，再使用 `Zoom In` / `Zoom Out` |
| 重置视图 | `Ctrl+R` / `Cmd+R` 或 `View` > `Reset View` |
| 配置波形设置 | `View` > `Waveform Setup...` |
| 选择渲染器 | `Display` > `Renderer` (`CPU` / `OpenGL`) |
| 切换 X 游标 | `X` 或 `X cursors` 复选框 |
| 切换 Y 游标 | `Y` 或 `Y cursors` 复选框 |
| 移动游标 | 拖拽虚线游标线或其标签 |
| 重置游标 | `Shift+R` 或 Cursors 页中的 `Reset Cursors` 按钮 |

当 Navigate 缩放控制选择 `Y` 时，缩放命令作用于当前活动 Y 控制组。按 `T` 或使用 `Y group` 菜单可在左轴和右轴之间切换。游标轴组在 Cursors 页中单独控制，因此切换活动 Y 控制组不会移动已有游标。

## Waveform Setup

加载波形文件后会打开 Waveform Setup，也可以从 View 菜单打开。它用于控制 X 轴时间基准以及每个波形的 Y 轴分配。

时间基准选项：

| 模式 | 行为 |
| --- | --- |
| `Time column` | 使用选定数字列作为 X 轴。该列必须是有限值且严格递增。非均匀间距允许使用但会给出警告；FFT 使用中位采样间隔。选中的时间列不会作为信号绘制。 |
| `Sample rate (Sa/s)` | 生成时间 `sample_index / sample_rate`。所有有效数字列，包括检测到的时间列，都会作为普通信号处理。 |
| `Sample interval (s/pt)` | 生成时间 `sample_index * sample_interval`。所有有效数字列，包括检测到的时间列，都会作为普通信号处理。 |
| `Sample index` | 使用 `0, 1, 2, ...` 作为 X 轴。所有有效数字列都会作为普通信号处理。 |

如果文件有检测到的时间列，你仍然可以用生成的时间基准覆盖它。此时检测到的时间列会变成普通信号，可像其他波形一样分配到轴或禁用。

波形表可以把每个信号分配到左轴、右轴或禁用状态，并可编辑轴单位和初始 Y 范围。

## Math

Math 页会从已加载波形创建仅当前会话有效的计算输出。加载新波形文件会清除计算波形和频谱。

### 时域计算波形

选择函数，选择操作数 `A`，如果是二元函数再选择操作数 `B`，然后输入或接受自动生成的输出名称并点击 `Add`。也可以点击操作数旁边的 `Pick`，再在主图中点击波形曲线来填入操作数。时域结果会作为普通波形加入，因此会出现在通道列表、图例、预览、轴设置、高亮和游标读数中。

计算得到的波形可以继续作为后续 Math 操作的操作数，因此可以通过组合多个简单输出构建更复杂的表达式。

支持的时域函数：

| 类型 | 函数 |
| --- | --- |
| 一元 | `A^2`, `sqrt(A)`, `abs(A)`, `log10(A)`, `ln(A)`, `-A`, `∫A dt`, `dA/dt` |
| 标量 | `a*A+b` |
| 二元 | `A+B`, `A-B`, `A*B`, `A/B` |

无效数值结果，例如除以零或负数平方根，会保留为非有限采样并被绘图跳过。

### FFT 频谱

选择 `FFT(A)` 可从波形 `A` 创建频域频谱。频谱会在 `Spectrum` 视图中打开，使用源波形颜色，并以 dB 对 Hz 绘制幅值。

FFT 控制：

| 控制 | 行为 |
| --- | --- |
| `Window` | 在 FFT 前应用 `Rectangular`、`Hann`、`Hamming` 或 `Cosine` 窗。 |
| `Remove DC offset` | 在加窗前减去所选片段均值，避免 DC 频点主导 Y 范围。 |
| `Zero pad` | 在所选片段后补零以生成更密的 FFT 频点。选项为 `None`、`Next power of 2`、`2x`、`4x` 和 `8x`。这只改善显示/插值密度，不提升真实频率分辨率。 |
| `Add` | 创建或替换指定名称的 FFT 频谱。 |
| `Update FFT` | 使用当前 X 游标范围、窗函数、DC 和补零设置重新计算所选频谱。 |
| `Min Hz` / `Max Hz` | 在不重新计算 FFT 的情况下筛选显示频率范围。 |

FFT 时间范围：

- 如果 X 游标隐藏，FFT 使用完整有限波形时间范围。
- 如果 X 游标可见，FFT 使用排序后的 `X1` 与 `X2` 区间。
- 移动 X 游标不会自动重新计算频谱；请点击 `Update FFT`。

频谱视图：

- 鼠标滚轮缩放频率。
- `Ctrl`/`Cmd` + 鼠标滚轮缩放幅值。
- 拖拽平移频率。
- `Ctrl`/`Cmd` + 拖拽平移幅值。
- 频率范围会限制在显示频谱范围内。
- 鼠标悬停在谱峰附近会显示频率和 dB 幅值。

点击 Math 输出列表中的项目会切换到对应视图。计算波形输出切换到 `Waveforms` 并高亮曲线；FFT 输出切换到 `Spectrum`。

## Measure

Measure 页用于为一个或多个波形信号显示可复用的测量卡片。你可以在波形选择器中选中信号并点击 `Add`，也可以点击 `Pick` 后在图中点击一条曲线来直接添加该信号。每个添加的信号都会拥有自己的卡片，并且每张卡片都会记住自己的测量范围和 SI 缩放设置。

测量范围：

- `Full` 测量完整的有限波形。
- `X cursors` 只测量排序后的 `X1` 与 `X2` 区间；移动 X 游标会更新所有使用游标范围的卡片。

每张卡片会在标题中使用对应信号的颜色，并把读数分为纵向测量和横向测量。纵向测量包含 Max、Min、Avg、Peak-to-peak、RMS 和 ACRMS。横向测量包含 Period 和 Frequency。数值会带合适的单位：纵向值使用信号单位，Period 使用 `s`，Frequency 使用 `Hz`。缩放选择器支持 `Auto`、`p`、`n`、`µ`、`m`、无前缀、`k`、`M`、`G` 和 `T`。

交互：

- 点击测量卡片可选中它，并编辑该信号自己的范围/缩放控件。
- 双击卡片可把该信号的测量读数分离到浮动窗口。
- 关闭浮动窗口会把卡片重新附加回 Measure 页。
- 右键点击卡片可从 Measure 页移除该信号。
- 整个 Measure 页仍可通过双击右侧标签栏中的 Measure 标签分离。

## 本地化

GUI 使用 Qt 原生翻译支持。英语是源语言和回退语言。

默认情况下，如果存在匹配的编译翻译文件，应用会使用操作系统语言。也可以显式传入启动语言：

```bash
python main.py --language zh_CN example_csv/1t1r_set_read_0P1V.csv
```

使用 `--language system` 可显式请求系统语言。

`Display` 菜单中也有 `Language` 选择器。选择其他语言后会提示重启，并用所选启动语言重新启动应用。

翻译文件位于 `translations/`：

- `cswave_en.ts` 是英语参考目录。
- `cswave_zh_CN.ts` / `.qm` 和 `cswave_ja_JP.ts` / `.qm` 提供中文和日文翻译。
- 翻译者可以添加其他 `cswave_<locale>.ts` 文件。
- 运行时编译文件命名为 `cswave_<locale>.qm`。

典型翻译流程：

```bash
pyside6-lupdate main.py viewer.py viewer_panels.py ui_common.py plot_widgets.py -ts translations/cswave_en.ts
pyside6-lupdate main.py viewer.py viewer_panels.py ui_common.py plot_widgets.py -ts translations/cswave_zh_CN.ts
pyside6-lupdate main.py viewer.py viewer_panels.py ui_common.py plot_widgets.py -ts translations/cswave_ja_JP.ts
pyside6-lrelease translations/cswave_zh_CN.ts -qm translations/cswave_zh_CN.qm
pyside6-lrelease translations/cswave_ja_JP.ts -qm translations/cswave_ja_JP.qm
```

## 构建发布包

发布包使用 PyInstaller 构建，并包含翻译、示例、README 和许可证文件。构建产物写入 `release/`。

Windows：

```powershell
.\scripts\build_windows.ps1
```

macOS：

```bash
./scripts/build_macos.sh
```

Linux：

```bash
./scripts/build_linux.sh
```

在 macOS/Linux 上设置 `SKIP_TESTS=1`，或在 Windows 上传入 `-SkipTests`，可跳过打包时的测试运行。

## 许可证

CSV Waveform Viewer 使用 MIT License 发布。详情见 [LICENSE](LICENSE)。
