#!/usr/bin/env bash
PLIST="$HOME/Library/LaunchAgents/com.sfa.stockfinder.plist"
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST" && echo "Removed (data in db/ is kept)."
