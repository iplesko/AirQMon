#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OPS_DIR="$SCRIPT_DIR"
BACKEND_DIR="$(cd -- "$OPS_DIR/.." && pwd)"
SYSTEMD_SOURCE_DIR="$OPS_DIR/systemd"

APP_USER="${SUDO_USER:-admin}"
INPUT_USER="root"
CONFIG_PATH="/etc/airqmon/airqmon.env"
LAUNCHER_PATH="/usr/local/bin/airqmon-launch"
SYSTEMD_DIR="/etc/systemd/system"
PYTHON_PATH="$BACKEND_DIR/venv/bin/python"
DB_PATH="$BACKEND_DIR/data.db"
APP_ENV_FILE="$BACKEND_DIR/.env"
WEB_HOST="0.0.0.0"
WEB_PORT="8000"
POLL_INTERVAL="5"
DISPLAY_BRIGHTNESS_GPIO="18"
PINCTRL_PATH="/usr/bin/pinctrl"
FORCE_CONFIG="0"
START_TARGET="0"

usage() {
    cat <<EOF
Usage: sudo bash backend/ops/install_systemd.sh [options]

Options:
  --app-user USER                User for collector, web, alerter, and display
  --input-user USER              User for input service (default: root)
  --python PATH                  Python interpreter path
  --db PATH                      SQLite database path
  --app-env-file PATH            Application env file used by web and alerter
  --web-host HOST                Uvicorn host (default: 0.0.0.0)
  --web-port PORT                Uvicorn port (default: 8000)
  --poll-interval SECONDS        Shared collector, alerter, and display interval
  --display-brightness-gpio PIN  GPIO used for display brightness cleanup
  --pinctrl PATH                 pinctrl binary path
  --config-path PATH             Shared AirQMon service config path
  --launcher-path PATH           Installed launcher path
  --systemd-dir PATH             systemd unit directory
  --force-config                 Overwrite an existing shared service config
  --start                        Enable and start airqmon.target after install
  --help                         Show this help text
EOF
}

log() {
    printf '%s\n' "$*" >&2
}

fail() {
    log "$*"
    exit 1
}

escape_sed_replacement() {
    printf '%s' "$1" | sed 's/[\/&]/\\&/g'
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --app-user)
                APP_USER="$2"
                shift 2
                ;;
            --input-user)
                INPUT_USER="$2"
                shift 2
                ;;
            --python)
                PYTHON_PATH="$2"
                shift 2
                ;;
            --db)
                DB_PATH="$2"
                shift 2
                ;;
            --app-env-file)
                APP_ENV_FILE="$2"
                shift 2
                ;;
            --web-host)
                WEB_HOST="$2"
                shift 2
                ;;
            --web-port)
                WEB_PORT="$2"
                shift 2
                ;;
            --poll-interval)
                POLL_INTERVAL="$2"
                shift 2
                ;;
            --display-brightness-gpio)
                DISPLAY_BRIGHTNESS_GPIO="$2"
                shift 2
                ;;
            --pinctrl)
                PINCTRL_PATH="$2"
                shift 2
                ;;
            --config-path)
                CONFIG_PATH="$2"
                shift 2
                ;;
            --launcher-path)
                LAUNCHER_PATH="$2"
                shift 2
                ;;
            --systemd-dir)
                SYSTEMD_DIR="$2"
                shift 2
                ;;
            --force-config)
                FORCE_CONFIG="1"
                shift
                ;;
            --start)
                START_TARGET="1"
                shift
                ;;
            --help)
                usage
                exit 0
                ;;
            *)
                usage
                fail "Unknown option: $1"
                ;;
        esac
    done
}

require_root() {
    if [[ "$EUID" -ne 0 ]]; then
        fail "Run this installer with sudo or as root."
    fi
}

validate_inputs() {
    command -v systemctl >/dev/null 2>&1 || fail "systemctl was not found. This installer is intended for systemd-based Linux systems."
    [[ -d "$BACKEND_DIR/src" ]] || fail "Missing source directory at $BACKEND_DIR/src"
    [[ -f "$OPS_DIR/airqmon-launch.sh" ]] || fail "Missing launcher script at $OPS_DIR/airqmon-launch.sh"
    [[ -f "$SYSTEMD_SOURCE_DIR/airqmon.target" ]] || fail "Missing target unit at $SYSTEMD_SOURCE_DIR/airqmon.target"
    [[ -f "$SYSTEMD_SOURCE_DIR/airqmon-collector.service" ]] || fail "Missing collector unit in $SYSTEMD_SOURCE_DIR"
    [[ -f "$SYSTEMD_SOURCE_DIR/airqmon-web.service" ]] || fail "Missing web unit in $SYSTEMD_SOURCE_DIR"
    [[ -f "$SYSTEMD_SOURCE_DIR/airqmon-alerter.service" ]] || fail "Missing alerter unit in $SYSTEMD_SOURCE_DIR"
    [[ -f "$SYSTEMD_SOURCE_DIR/airqmon-display.service" ]] || fail "Missing display unit in $SYSTEMD_SOURCE_DIR"
    [[ -f "$SYSTEMD_SOURCE_DIR/airqmon-input.service" ]] || fail "Missing input unit in $SYSTEMD_SOURCE_DIR"
    [[ -x "$PYTHON_PATH" ]] || fail "Python interpreter was not found or is not executable: $PYTHON_PATH"
}

render_unit() {
    local source_path="$1"
    local target_path="$2"
    local service_user="$3"
    local escaped_user

    escaped_user="$(escape_sed_replacement "$service_user")"
    sed "s/^User=.*/User=${escaped_user}/" "$source_path" >"$target_path"
}

write_config() {
    local config_dir
    config_dir="$(dirname -- "$CONFIG_PATH")"
    install -d -m 755 "$config_dir"

    if [[ -f "$CONFIG_PATH" && "$FORCE_CONFIG" != "1" ]]; then
        log "Keeping existing AirQMon service config at $CONFIG_PATH"
        return
    fi

    cat >"$CONFIG_PATH" <<EOF
# Shared runtime settings used by the AirQMon systemd wrapper.
AIRQMON_BACKEND_DIR=$BACKEND_DIR
AIRQMON_PYTHON=$PYTHON_PATH
AIRQMON_DB_PATH=$DB_PATH
AIRQMON_APP_ENV_FILE=$APP_ENV_FILE

AIRQMON_WEB_HOST=$WEB_HOST
AIRQMON_WEB_PORT=$WEB_PORT

AIRQMON_POLL_INTERVAL=$POLL_INTERVAL

AIRQMON_DISPLAY_BRIGHTNESS_GPIO=$DISPLAY_BRIGHTNESS_GPIO
AIRQMON_PINCTRL=$PINCTRL_PATH
EOF
    chmod 644 "$CONFIG_PATH"
    log "Wrote AirQMon service config to $CONFIG_PATH"
}

install_launcher() {
    install -d -m 755 "$(dirname -- "$LAUNCHER_PATH")"
    install -m 755 "$OPS_DIR/airqmon-launch.sh" "$LAUNCHER_PATH"
    log "Installed launcher to $LAUNCHER_PATH"
}

install_units() {
    local tmp_dir
    tmp_dir="$(mktemp -d)"
    trap 'rm -rf -- "$tmp_dir"' EXIT

    render_unit "$SYSTEMD_SOURCE_DIR/airqmon-collector.service" "$tmp_dir/airqmon-collector.service" "$APP_USER"
    render_unit "$SYSTEMD_SOURCE_DIR/airqmon-web.service" "$tmp_dir/airqmon-web.service" "$APP_USER"
    render_unit "$SYSTEMD_SOURCE_DIR/airqmon-alerter.service" "$tmp_dir/airqmon-alerter.service" "$APP_USER"
    render_unit "$SYSTEMD_SOURCE_DIR/airqmon-display.service" "$tmp_dir/airqmon-display.service" "$APP_USER"
    render_unit "$SYSTEMD_SOURCE_DIR/airqmon-input.service" "$tmp_dir/airqmon-input.service" "$INPUT_USER"

    install -d -m 755 "$SYSTEMD_DIR"
    install -m 644 "$tmp_dir/airqmon-collector.service" "$SYSTEMD_DIR/airqmon-collector.service"
    install -m 644 "$tmp_dir/airqmon-web.service" "$SYSTEMD_DIR/airqmon-web.service"
    install -m 644 "$tmp_dir/airqmon-alerter.service" "$SYSTEMD_DIR/airqmon-alerter.service"
    install -m 644 "$tmp_dir/airqmon-display.service" "$SYSTEMD_DIR/airqmon-display.service"
    install -m 644 "$tmp_dir/airqmon-input.service" "$SYSTEMD_DIR/airqmon-input.service"
    install -m 644 "$SYSTEMD_SOURCE_DIR/airqmon.target" "$SYSTEMD_DIR/airqmon.target"
    log "Installed AirQMon systemd units into $SYSTEMD_DIR"
}

reload_systemd() {
    systemctl daemon-reload
    systemctl enable airqmon.target
    if [[ "$START_TARGET" == "1" ]]; then
        systemctl start airqmon.target
        log "Enabled and started airqmon.target"
    else
        log "Enabled airqmon.target"
    fi
}

print_notes() {
    if [[ ! -f "$APP_ENV_FILE" ]]; then
        log "Warning: $APP_ENV_FILE does not exist yet. Create it from backend/.env.sample before relying on web push alerts."
    fi

    cat <<EOF

AirQMon systemd wrapper installed.

Shared config:
  $CONFIG_PATH

Aggregate target:
  sudo systemctl status airqmon.target
  sudo systemctl restart airqmon.target

Individual logs:
  sudo journalctl -u airqmon-web -f
  sudo journalctl -u airqmon-display -f
EOF
}

main() {
    parse_args "$@"
    require_root
    validate_inputs
    install_launcher
    write_config
    install_units
    reload_systemd
    print_notes
}

main "$@"
