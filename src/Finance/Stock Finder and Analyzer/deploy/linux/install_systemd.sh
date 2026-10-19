#!/usr/bin/env bash
# Installs a systemd *user* service that starts at log-in (and at boot with lingering)
# and restarts if it stops.   bash deploy/linux/install_systemd.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
UNIT="$HOME/.config/systemd/user/sfa.service"
mkdir -p "$(dirname "$UNIT")" "$ROOT/logs"
cat > "$UNIT" <<UN
[Unit]
Description=Stock Finder and Analyzer (scheduler + dashboard on http://localhost:8000)
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$ROOT
ExecStart=$PY -m sfa start
Restart=always
RestartSec=60
StandardOutput=append:$ROOT/logs/sfa.log
StandardError=append:$ROOT/logs/sfa.log

[Install]
WantedBy=default.target
UN
systemctl --user daemon-reload
systemctl --user enable --now sfa.service
echo "Installed $UNIT and started it. Dashboard: http://localhost:8000  Log: $ROOT/logs/sfa.log"
echo "To keep it running when you are logged out:  sudo loginctl enable-linger $USER"
echo "Keys are read from $ROOT/sfa.env."
