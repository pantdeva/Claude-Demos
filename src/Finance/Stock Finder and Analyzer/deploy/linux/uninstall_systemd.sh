#!/usr/bin/env bash
systemctl --user disable --now sfa.service 2>/dev/null || true
rm -f "$HOME/.config/systemd/user/sfa.service" && systemctl --user daemon-reload && echo "Removed (data in db/ is kept)."
