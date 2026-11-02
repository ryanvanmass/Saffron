#!/usr/bin/env bash
# Builds Saffron.app and a .dmg for macOS. The bundle carries Saffron's own
# Python sources and a launcher; PySide6, PyGObject and spice-glib come
# from Homebrew at runtime (see launcher.sh for why). Pure Python + shell,
# so the same bundle runs on Apple Silicon and Intel.
#
# Requires macOS (codesign, hdiutil) and python3 >= 3.11. Runnable
# standalone; .github/workflows/macos.yml runs exactly this.
set -euo pipefail
cd "$(dirname "$0")/../.."  # repo root

VERSION=$(python3 -c "import re; print(re.search(r'__version__ = \"(.+?)\"', open('src/saffron/__init__.py').read())[1])")
SHORT_VERSION="${VERSION%%-*}"   # CFBundleShortVersionString wants plain dotted numbers

BUILD_DIR=build/macos
APP="$BUILD_DIR/Saffron.app"
DMG="dist/Saffron-${VERSION}-macos.dmg"

if [[ "$(uname -s)" != Darwin ]]; then
    echo "This script builds a macOS .app and must run on macOS." >&2
    exit 1
fi

echo "Building Saffron $VERSION for macOS..."
rm -rf "$BUILD_DIR"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/app" dist

# Sources only: no tests, no caches.
rsync -a --exclude '__pycache__' --exclude '*.pyc' src/saffron "$APP/Contents/Resources/app/"
cp packaging/macos/launcher.sh "$APP/Contents/MacOS/saffron"
chmod +x "$APP/Contents/MacOS/saffron"
cp assets/saffron.icns "$APP/Contents/Resources/saffron.icns"
sed -e "s/@VERSION@/$VERSION/g" -e "s/@SHORT_VERSION@/$SHORT_VERSION/g" \
    packaging/macos/Info.plist.in > "$APP/Contents/Info.plist"
plutil -lint "$APP/Contents/Info.plist"

# Ad-hoc signature: no Developer ID needed, but Gatekeeper still asks on
# first launch (right-click > Open), as with IT Toolbox's .dmg.
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

rm -f "$DMG"
STAGE="$BUILD_DIR/dmg"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "Saffron $VERSION" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
echo "Built $APP and $DMG"
