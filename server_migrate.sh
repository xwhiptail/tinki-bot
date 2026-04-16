#!/usr/bin/env bash
set -euo pipefail

UNIT=/etc/systemd/system/tinki-bot.service
ENVF=/etc/tinki-bot.env
APP_ROOT=/opt/apps/tinki-bot
REPO_DIR="$APP_ROOT/repo"
DATA_DIR="$APP_ROOT/data"
PYTHON_BIN="$APP_ROOT/myenv/bin/python3.8"
TS="$(date +%Y%m%d%H%M%S)"

OPENAI_KEY="$(
  sudo awk -F'"' '/Environment="OPENAI_API_KEY=/{print $2}' "$UNIT" \
  | sed 's/^OPENAI_API_KEY=//'
)"

sudo cp -a "$UNIT" "${UNIT}.bak.${TS}"
sudo cp -a "$ENVF" "${ENVF}.bak.${TS}"

tmp_env="$(mktemp)"
sudo sed '/^MINECRAFT_EC2=/d;/^SKYFACTORY_EC2=/d;/^OPENAI_MODEL=/d;/^TINKI_DATA_DIR=/d;/^OPENAI_API_KEY=/d' \
  "$ENVF" > "$tmp_env"

if [ -n "$OPENAI_KEY" ]; then
  printf 'OPENAI_API_KEY=%s\n' "$OPENAI_KEY" >> "$tmp_env"
fi

printf 'OPENAI_MODEL=gpt-5.4-mini\n' >> "$tmp_env"
printf 'TINKI_DATA_DIR=%s\n' "$DATA_DIR" >> "$tmp_env"

sudo install -m 600 "$tmp_env" "$ENVF"
rm -f "$tmp_env"

cat > /tmp/tinki-bot.service.new <<EOF
[Unit]
Description=Tinki Discord Bot
After=network.target

[Service]
Type=simple
User=ec2-user
Group=ec2-user
WorkingDirectory=$REPO_DIR
EnvironmentFile=$ENVF
ExecStart=$PYTHON_BIN $REPO_DIR/tinki-bot.py
Restart=always
RestartSec=5
TimeoutStopSec=90s

[Install]
WantedBy=multi-user.target
EOF

sudo mv /tmp/tinki-bot.service.new "$UNIT"
sudo chown root:root "$UNIT"
sudo chmod 644 "$UNIT"
sudo systemctl daemon-reload
sudo systemctl restart tinki-bot
sleep 3
sudo systemctl status tinki-bot --no-pager
