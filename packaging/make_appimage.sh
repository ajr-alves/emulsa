#!/usr/bin/env bash
# Packs dist/Emulsa (the PyInstaller folder build) into dist/Emulsa-<version>-x86_64.AppImage.
# Run on Linux after: pyinstaller --noconfirm --clean packaging/emulsa.spec
# Needs appimagetool: set APPIMAGETOOL to its path, or it is downloaded from the AppImage project on GitHub.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=$(python3 -c "import emulsa; print(emulsa.__version__)")
ARCH=$(uname -m)
SRC="dist/Emulsa"
APPDIR="build/Emulsa.AppDir"
OUT="dist/Emulsa-${VERSION}-${ARCH}.AppImage"

[ -x "$SRC/Emulsa" ] || { echo "Missing $SRC/Emulsa. Build it with PyInstaller first."; exit 1; }

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib/emulsa" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/512x512/apps"
cp -R "$SRC/." "$APPDIR/usr/lib/emulsa/"
cp packaging/emulsa.desktop "$APPDIR/emulsa.desktop"
cp packaging/emulsa.desktop "$APPDIR/usr/share/applications/emulsa.desktop"
cp emulsa/assets/emulsa-512.png "$APPDIR/emulsa.png"
cp emulsa/assets/emulsa-512.png "$APPDIR/usr/share/icons/hicolor/512x512/apps/emulsa.png"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/emulsa/Emulsa" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# appimagetool is pinned to one release and checked against its SHA-256, so a changed download is refused
TOOL_VERSION="1.9.1"
TOOL_SHA256_x86_64="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"
TOOL="${APPIMAGETOOL:-}"
if [ -z "$TOOL" ]; then
  [ "$ARCH" = "x86_64" ] || { echo "No pinned appimagetool for $ARCH. Set APPIMAGETOOL to a trusted copy."; exit 1; }
  TOOL="build/appimagetool-${TOOL_VERSION}-${ARCH}.AppImage"
  if [ ! -x "$TOOL" ]; then
    curl -fsSL -o "$TOOL.part" "https://github.com/AppImage/appimagetool/releases/download/${TOOL_VERSION}/appimagetool-${ARCH}.AppImage"
    echo "${TOOL_SHA256_x86_64}  $TOOL.part" | sha256sum -c - || { rm -f "$TOOL.part"; echo "appimagetool checksum mismatch. Stopping."; exit 1; }
    mv "$TOOL.part" "$TOOL"
    chmod +x "$TOOL"
  fi
fi

rm -f "$OUT"
# --appimage-extract-and-run lets appimagetool run without FUSE (CI machines, containers)
ARCH="$ARCH" "$TOOL" --appimage-extract-and-run "$APPDIR" "$OUT"
echo "Built $OUT"
