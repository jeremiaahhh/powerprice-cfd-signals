#!/usr/bin/env bash
# Uninstall the PowerPrice Signal Daemon LaunchAgent.

set -euo pipefail

PLIST_LABEL="com.powerprice.signal-daemon"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"

echo "=== PowerPrice Signal Daemon — macOS Uninstall ==="

if [[ ! -f "$PLIST_DST" ]]; then
    echo "Agent not installed (plist not found at $PLIST_DST)."
    exit 0
fi

echo "Stopping agent..."
launchctl unload -w "$PLIST_DST" 2>/dev/null || true

echo "Removing plist..."
rm -f "$PLIST_DST"

echo "Done. Daemon stopped and LaunchAgent removed."
echo "Data files in ./data/ are preserved."
