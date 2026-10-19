#!/usr/bin/env bash
# Installs a launchd agent that starts the service at log-in and restarts it if it stops.
#   bash deploy/macos/install_launchd.sh        (from the "Stock Finder and Analyzer" folder or anywhere)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
LABEL="com.sfa.stockfinder"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$ROOT/logs" "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>-m</string><string>sfa</string><string>start</string></array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>60</integer>
  <key>StandardOutPath</key><string>$ROOT/logs/sfa.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/sfa.log</string>
</dict></plist>
PL
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Installed $PLIST. Dashboard: http://localhost:8000  Log: $ROOT/logs/sfa.log"
echo "Keys are read from $ROOT/sfa.env (launchd does not see your shell's exported variables)."
