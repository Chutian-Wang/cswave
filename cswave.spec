# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from app_info import APP_ID, APP_NAME, APP_VERSION


ROOT = Path(SPECPATH)


def add_tree(directory: str, target: str) -> list[tuple[str, str]]:
    base = ROOT / directory
    if not base.exists():
        return []
    return [
        (str(path), str(Path(target) / path.relative_to(base).parent))
        for path in base.rglob("*")
        if path.is_file()
    ]


datas = []
datas += add_tree("translations", "translations")
datas += add_tree("example_csv", "example_csv")
for filename in ("README.md", "LICENSE"):
    path = ROOT / filename
    if path.exists():
        datas.append((str(path), "."))


a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=["openpyxl", "xlrd"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "packaging" / "pyi_rth_preload_data_stack.py")],
    excludes=["pytest"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_ID,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_ID,
)

app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon=None,
    bundle_identifier="org.cswave.viewer",
    info_plist={
        "CFBundleDisplayName": APP_NAME,
        "CFBundleName": APP_NAME,
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_VERSION,
        "NSHighResolutionCapable": True,
    },
)
