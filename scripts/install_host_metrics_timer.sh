#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${TINKI_REPO_DIR:-/opt/apps/tinki-bot/repo}"
VENV_PYTHON="${TINKI_VENV_PYTHON:-/opt/apps/tinki-bot/myenv/bin/python}"
SERVICE_NAME="${TINKI_HOST_METRICS_SERVICE:-tinki-host-metrics}"
ENV_FILE="${TINKI_ENV_FILE:-/etc/tinki-bot.env}"

sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" >/dev/null <<EOF
[Unit]
Description=Publish tinki-bot host metrics to CloudWatch
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=tinki-bot
WorkingDirectory=${REPO_DIR}
EnvironmentFile=-${ENV_FILE}
ExecStart=${VENV_PYTHON} ${REPO_DIR}/scripts/publish_host_metrics.py
EOF

sudo tee "/etc/systemd/system/${SERVICE_NAME}.timer" >/dev/null <<EOF
[Unit]
Description=Run tinki-bot host metrics publisher every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
AccuracySec=1min
Unit=${SERVICE_NAME}.service

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now "${SERVICE_NAME}.timer"
sudo systemctl status "${SERVICE_NAME}.timer" --no-pager
