#!/usr/bin/env bash
# Checks a built Saffron.app actually starts on this Mac's Homebrew stack,
# always through the app's real launcher: signature, the full native
# import chain (PySide6 + PyGObject + spice-glib), argument handling, and
# a headless run that must fail cleanly (exit 1, no crash or hang)
# against a closed port.
set -euo pipefail
cd "$(dirname "$0")/../.."
APP=build/macos/Saffron.app
EXE="$APP/Contents/MacOS/saffron"

echo "--- signature"
codesign --verify --deep --strict "$APP"

echo "--- native stack"
"$EXE" --self-test

echo "--- version"
"$EXE" --version | grep -q "^saffron "

echo "--- bad input exits 2"
set +e
"$EXE" --connect qemu:///system
rc=$?
set -e
[[ $rc -eq 2 ]] || { echo "expected exit 2, got $rc"; exit 1; }

echo "--- headless connect to a closed port fails cleanly"
set +e
QT_QPA_PLATFORM=offscreen SAFFRON_NO_DIALOGS=1 "$EXE" spice://127.0.0.1:1 &
pid=$!
for _ in $(seq 60); do kill -0 $pid 2>/dev/null || break; sleep 1; done
if kill -0 $pid 2>/dev/null; then kill $pid; echo "still running after 60s"; exit 1; fi
wait $pid
rc=$?
set -e
[[ $rc -eq 1 ]] || { echo "expected exit 1, got $rc"; exit 1; }
echo "Smoke test passed."
