# Release Checklist

CSV Waveform Viewer releases are packaged with PyInstaller for each target OS.

## Version

Update `APP_VERSION` in `app_info.py`. Build scripts read this value when naming release artifacts.

## Build

Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

macOS:

```bash
./scripts/build_macos.sh
```

Linux:

```bash
./scripts/build_linux.sh
```

GitHub Actions also builds all three platforms for tags matching `v*`.

## Validate

- Launch the packaged app by double-clicking it.
- Open at least one CSV example.
- Open at least one XLS/XLSX example.
- Confirm translations load with `--language zh_CN` and `--language ja_JP`.
- Confirm `Help` > `About CSV Waveform Viewer` shows the correct version and MIT license.
- Confirm Math FFT, cursor picking, channel drag/drop, detachable panels, and Waveform Setup still work.
- On macOS, verify first-launch Gatekeeper behavior is documented in release notes.

## Publish

- Attach `release/` artifacts to the GitHub release.
- Include the matching source archive.
- Mention that builds are unsigned unless code signing has been configured.
