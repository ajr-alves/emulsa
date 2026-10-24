#!/usr/bin/env bash
# Packs dist/Emulsa.app into dist/Emulsa-<version>-macOS-<arch>.dmg with a drag-to-Applications layout.
# Run on macOS after: pyinstaller --noconfirm --clean packaging/emulsa.spec
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=$(python3 -c "import emulsa; print(emulsa.__version__)")
ARCH=$(uname -m)
APP="dist/Emulsa.app"
OUT="dist/Emulsa-${VERSION}-macOS-${ARCH}.dmg"

[ -d "$APP" ] || { echo "Missing $APP. Build it with PyInstaller first."; exit 1; }

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"

rm -f "$OUT"
hdiutil create -volname "Emulsa" -srcfolder "$STAGE" -ov -format UDZO "$OUT"
echo "Built $OUT"
