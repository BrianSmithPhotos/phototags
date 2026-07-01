#!/bin/bash
# Convert a single 1024x1024 PNG into resources/AppIcon.icns for the py2app build.
# Usage: scripts/make_icns.sh path/to/icon-1024.png
set -euo pipefail

if [ $# -ne 1 ]; then
    echo "Usage: $0 <path-to-1024x1024.png>" >&2
    exit 1
fi

SRC="$1"
ICONSET_DIR="resources/AppIcon.iconset"

mkdir -p "$ICONSET_DIR"
sips -z 16 16 "$SRC" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null
sips -z 32 32 "$SRC" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null
sips -z 32 32 "$SRC" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null
sips -z 64 64 "$SRC" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null
sips -z 128 128 "$SRC" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null
sips -z 256 256 "$SRC" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null
sips -z 256 256 "$SRC" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null
sips -z 512 512 "$SRC" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null
sips -z 512 512 "$SRC" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null
cp "$SRC" "$ICONSET_DIR/icon_512x512@2x.png"

iconutil -c icns "$ICONSET_DIR" -o resources/AppIcon.icns
rm -rf "$ICONSET_DIR"

echo "Wrote resources/AppIcon.icns"
