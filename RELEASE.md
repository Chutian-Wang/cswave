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

GitHub Actions builds all three platforms for tags matching `v*`, verifies that every platform artifact was generated, and creates the GitHub release automatically.

## Validate

- Launch the packaged app by double-clicking it.
- Open at least one CSV example.
- Open at least one XLS/XLSX example.
- Confirm translations load with `--language zh_CN` and `--language ja_JP`.
- Confirm `Help` > `About CSV Waveform Viewer` shows the correct version and MIT license.
- Confirm Math FFT, cursor picking, channel drag/drop, detachable panels, and Waveform Setup still work.
- On macOS, verify first-launch Gatekeeper behavior is documented in release notes.

## Publish

- Push a tag matching `v*`, such as `v0.2.0`.
- Wait for the release workflow to finish successfully; it will attach the Windows, macOS, and Linux artifacts to the GitHub release.
- Mention that builds are unsigned unless code signing has been configured.
