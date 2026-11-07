#!/bin/bash
# Builds djnext.app and djnext.dmg (drag-to-Applications installer) for Macs with the same chip as this one.
#   packaging/mac/build_app.sh           -> dist/djnext.app and dist/djnext.dmg
# Needs: Python 3.10+ (e.g. `brew install python@3.12`). Everything else is installed into build/mac-venv.
set -euo pipefail
cd "$(dirname "$0")/../.."
ROOT="$PWD"
PY="${PYTHON:-$(command -v python3.12 || command -v python3.13 || command -v python3)}"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)"
ARCH="$(uname -m)"
BUILD="$ROOT/build/mac"
DIST="$ROOT/dist"
echo "==> djnext $VERSION for $ARCH, using $("$PY" --version)"

# 1. A clean build environment, separate from your normal .venv
if [ ! -x "$BUILD/venv/bin/python" ]; then "$PY" -m venv "$BUILD/venv"; fi
"$BUILD/venv/bin/pip" install -q --upgrade pip
"$BUILD/venv/bin/pip" install -q ".[mac]" pyinstaller

# 2. App icon: icon.png (1024x1024) -> djnext.icns
ICONSET="$BUILD/djnext.iconset"
rm -rf "$ICONSET" && mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z $s $s packaging/mac/icon.png --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) packaging/mac/icon.png --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$BUILD/djnext.icns"

# 3. Freeze Python + djnext + its libraries into djnext.app
rm -rf "$DIST/djnext.app"
"$BUILD/venv/bin/pyinstaller" --noconfirm --clean --windowed --log-level WARN \
  --name djnext --icon "$BUILD/djnext.icns" \
  --osx-bundle-identifier io.github.ayshsudhir.djnext \
  --distpath "$DIST" --workpath "$BUILD/work" --specpath "$BUILD" \
  --add-data "$ROOT/config.yaml:." \
  --collect-data djnext \
  --collect-all pyrekordbox --collect-all sqlcipher3 \
  --collect-submodules yt_dlp --collect-all webview \
  --hidden-import uvicorn.logging --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols.http.auto --hidden-import uvicorn.lifespan.on \
  packaging/mac/launcher.py

# 4. Version, display name and macOS settings in Info.plist, then sign (ad-hoc: free, no Apple account)
PLIST="$DIST/djnext.app/Contents/Info.plist"
plutil -replace CFBundleShortVersionString -string "$VERSION" "$PLIST"
plutil -replace CFBundleVersion -string "$VERSION" "$PLIST"
plutil -replace CFBundleDisplayName -string "djnext" "$PLIST"
plutil -replace LSApplicationCategoryType -string "public.app-category.music" "$PLIST"
plutil -replace NSHighResolutionCapable -bool true "$PLIST"
plutil -replace LSMinimumSystemVersion -string "11.0" "$PLIST"
plutil -replace NSHumanReadableCopyright -string "MIT licence. Not affiliated with Pioneer DJ, AlphaTheta, rekordbox or SoundCloud." "$PLIST"
codesign --force --deep --sign - "$DIST/djnext.app"

# 5. The installer: a disk image with the app and a shortcut to Applications to drag it onto
DMG="$DIST/djnext.dmg"  # stable name: README links to releases/latest/download/djnext.dmg
STAGE="$BUILD/dmg"
rm -rf "$STAGE" "$DMG" && mkdir -p "$STAGE"
cp -R "$DIST/djnext.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -quiet -volname "djnext" -srcfolder "$STAGE" -fs HFS+ -format UDZO "$DMG"
echo "==> Done:"
echo "    App:       $DIST/djnext.app"
echo "    Installer: $DMG ($(du -h "$DMG" | cut -f1))"
