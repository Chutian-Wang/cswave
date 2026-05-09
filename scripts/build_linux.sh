#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"

cd "$ROOT"
VERSION="$("$PYTHON" -c 'from app_info import APP_VERSION; print(APP_VERSION)')"
"$PYTHON" -m pip install -r requirements.txt -r requirements-build.txt
if [[ "${SKIP_TESTS:-0}" != "1" ]]; then
  "$PYTHON" -m pytest
fi
"$PYTHON" -m PyInstaller --noconfirm --clean cswave.spec

mkdir -p release
tar -C dist -czf "release/cswave-${VERSION}-linux-x64.tar.gz" cswave
echo "Created release/cswave-${VERSION}-linux-x64.tar.gz"
