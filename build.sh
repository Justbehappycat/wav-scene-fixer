#!/bin/bash
# Build the standalone macOS app (PyInstaller) into dist/.
# Requires: python3. Creates a throwaway venv in .build-venv.
set -euo pipefail
cd "$(dirname "$0")"

VENV=.build-venv
[ -x "$VENV/bin/pyinstaller" ] || {
    python3 -m venv "$VENV"
    "$VENV/bin/pip" -q install pyinstaller
}

"$VENV/bin/pyinstaller" --noconfirm --windowed \
    --name "WAV Scene Fixer" \
    --osx-bundle-identifier com.justbehappycat.wavscenefixer \
    gui.py

( cd dist && ditto -c -k --keepParent "WAV Scene Fixer.app" "WAV-Scene-Fixer-macOS-arm64.zip" )
echo "Built: dist/WAV Scene Fixer.app  (zip: dist/WAV-Scene-Fixer-macOS-arm64.zip)"
