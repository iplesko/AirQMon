#!/usr/bin/env bash

set -euo pipefail

CONFIG_FILE="${AIRQMON_SERVICE_CONFIG:-/etc/airqmon/airqmon.env}"

log() {
    printf '%s\n' "$*" >&2
}

load_env_file() {
    local env_file="$1"
    set -a
    # shellcheck disable=SC1090
    . "$env_file"
    set +a
}

require_var() {
    local var_name="$1"
    if [[ -z "${!var_name:-}" ]]; then
        log "Missing required setting $var_name in $CONFIG_FILE"
        exit 78
    fi
}

load_service_config() {
    if [[ -f "$CONFIG_FILE" && -z "${AIRQMON_BACKEND_DIR:-}" ]]; then
        load_env_file "$CONFIG_FILE"
    fi

    require_var AIRQMON_BACKEND_DIR
    require_var AIRQMON_PYTHON
    require_var AIRQMON_DB_PATH

    AIRQMON_SRC_DIR="${AIRQMON_BACKEND_DIR}/src"
    AIRQMON_APP_ENV_FILE="${AIRQMON_APP_ENV_FILE:-${AIRQMON_BACKEND_DIR}/.env}"
    AIRQMON_WEB_HOST="${AIRQMON_WEB_HOST:-0.0.0.0}"
    AIRQMON_WEB_PORT="${AIRQMON_WEB_PORT:-8000}"
    AIRQMON_POLL_INTERVAL="${AIRQMON_POLL_INTERVAL:-5}"
    AIRQMON_DISPLAY_BRIGHTNESS_GPIO="${AIRQMON_DISPLAY_BRIGHTNESS_GPIO:-18}"
    AIRQMON_PINCTRL="${AIRQMON_PINCTRL:-/usr/bin/pinctrl}"
}

load_app_env() {
    if [[ ! -f "$AIRQMON_APP_ENV_FILE" ]]; then
        log "AirQMon application env file not found: $AIRQMON_APP_ENV_FILE"
        exit 78
    fi

    load_env_file "$AIRQMON_APP_ENV_FILE"
}

configure_pythonpath() {
    export PYTHONPATH="${AIRQMON_SRC_DIR}${PYTHONPATH:+:${PYTHONPATH}}"
}

run_python_module() {
    local module_name="$1"
    shift
    cd "$AIRQMON_BACKEND_DIR"
    configure_pythonpath
    exec "$AIRQMON_PYTHON" -m "$module_name" "$@"
}

run_web() {
    load_app_env
    cd "$AIRQMON_BACKEND_DIR"
    configure_pythonpath
    exec "$AIRQMON_PYTHON" -m uvicorn server:app --host "$AIRQMON_WEB_HOST" --port "$AIRQMON_WEB_PORT"
}

display_stop() {
    if [[ ! -x "$AIRQMON_PINCTRL" ]]; then
        log "Skipping display pin cleanup because pinctrl was not found at $AIRQMON_PINCTRL"
        exit 0
    fi

    "$AIRQMON_PINCTRL" set "$AIRQMON_DISPLAY_BRIGHTNESS_GPIO" op dl pd
}

main() {
    if [[ $# -ne 1 ]]; then
        log "Usage: $0 <collector|web|alerter|display|input|display-stop>"
        exit 64
    fi

    local service_name="$1"
    load_service_config

    case "$service_name" in
        collector)
            run_python_module collector --db "$AIRQMON_DB_PATH" --interval "$AIRQMON_POLL_INTERVAL"
            ;;
        web)
            run_web
            ;;
        alerter)
            load_app_env
            run_python_module alerter --db "$AIRQMON_DB_PATH" --poll-interval "$AIRQMON_POLL_INTERVAL"
            ;;
        display)
            run_python_module display --db "$AIRQMON_DB_PATH" --interval "$AIRQMON_POLL_INTERVAL"
            ;;
        input)
            run_python_module input
            ;;
        display-stop)
            display_stop
            ;;
        *)
            log "Unknown AirQMon service: $service_name"
            exit 64
            ;;
    esac
}

main "$@"
