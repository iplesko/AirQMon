# Backend

## Overview

Backend layout:

- `src/`: Python source code and bundled runtime assets
- `ops/`: deployment scripts and `systemd` unit files

The backend has five runtime processes:

- `src/collector.py`: reads sensor values (CO2, temperature, humidity) and stores them in SQLite.
- `src/server.py`: exposes REST endpoints and optionally serves the built frontend from `../frontend/dist`.
- `src/alerter.py`: watches new measurements in SQLite and sends Web Push alerts (VAPID) when CO2 is high.
- `src/display.py`: compatibility entrypoint for the local SPI display app in `src/display_app/`.
- `src/input.py`: owns the capacitive touch button, toggles display layouts, and powers off the Pi on a 5-second hold.

Tested hardware setup:

- Raspberry Pi Zero 2 W
- DFRobot SEN0536 (SCD41 infrared CO2 sensor)
- Waveshare 2.4" IPS TFT LCD module (240x320, SPI, ILI9341 controller)
- Grove Touch Sensor (capacitive touch button)
- Sensor uses I2C GPIO pins
- Display uses SPI GPIO pins plus PWM/control GPIOs
- Touch button uses a single GPIO input handled by the input service for local layout switching and 5-second hold shutdown

## Components

### Data Collector (`src/collector.py`)

- Reads from SCD4X (`scd4x` package) when available.
- Falls back to simulated values if sensor/driver is unavailable.
- Writes to `data.db` (default) every `--interval` seconds (default: `10`).
- Prunes data older than 7 days once per hour.

CLI options:

- `--db`: SQLite file path (default: `backend/data.db`)
- `--interval`: collection interval in seconds (default: `10.0`)

### API Server (`src/server.py`)

Endpoints:

- `GET /api/latest`: latest measurement row.
- `GET /api/data?start=<unix>&end=<unix>&points=<n>`:
  - `start`/`end` are optional UNIX timestamps.
  - Defaults to the last 24 hours when omitted.
  - `points` defaults to `500`, max `10000`, and downsamples evenly.
- `GET /api/config`: returns runtime config (`co2_high`, `co2_clear`, `cooldown_seconds`, `display_brightness`, `night_mode_enabled`).
- `PUT /api/config`: replaces runtime config values (`co2_high`, `co2_clear`, `cooldown_seconds`) and optionally updates `display_brightness` and `night_mode_enabled`.
- `GET /api/push/public-key`: returns configured VAPID public key for browser subscription.
- `POST /api/push/subscribe`: upserts browser push subscription (`endpoint`, `keys.p256dh`, `keys.auth`).
- `POST /api/push/unsubscribe`: removes a stored browser subscription by endpoint.

Static serving:

- If `frontend/dist` exists, the backend serves it at `/`.
- If it does not exist, API routes still work, but no frontend static files are served.

### Alert Worker (`src/alerter.py`)

- Polls the same SQLite DB for newly inserted measurements.
- Sends Web Push notifications when CO2 crosses a high threshold.
- Sends a recovery notification when CO2 returns below a clear threshold.
- Persists alert state (`last_seen_id`, `in_alert`, `last_alert_ts`) in DB, so restarts do not spam.

CLI options (selected):

- `--db`: SQLite file path (default: `backend/data.db`)
- `--poll-interval`: seconds between DB polls (default: `5`)

### Local Display (`src/display.py`, `src/display_app/`)

- Reads the latest stored measurement plus trend data from SQLite.
- Renders the Waveshare SPI display locally on the Raspberry Pi.
- Supports multiple on-device layouts.
- Receives local layout-toggle requests from `src/input.py`.
- Applies configurable display brightness and optional night mode.

CLI options:

- `--db`: SQLite file path (default: `backend/data.db`)
- `--interval`: refresh interval in seconds (default: `5.0`)

### Local Input (`src/input.py`)

- Owns the Grove Touch Sensor on `GPIO24` (physical pin `18`).
- A touch switches layouts immediately by signaling the display process on button press.
- A 5-second hold requests a full Raspberry Pi shutdown.
- Intended to run as `root` when you want shutdown support.

## Requirements

- Python 3
- `pip`
- Linux systemd (only if running as services)

Set VAPID environment variables before running `alerter.py` and `server.py` from `src/`:

- `AIRQMON_VAPID_PUBLIC_KEY_FILE`
- `AIRQMON_VAPID_PRIVATE_KEY_FILE`
- `AIRQMON_VAPID_SUBJECT` (recommended format: `mailto:you@example.com`)

Use the sample env file:

```bash
cd backend
cp .env.sample .env
```

Then edit `.env` and set real values for all `AIRQMON_VAPID_*` variables.

### Generate VAPID Keys on Debian / Raspberry Pi

From `backend/`:

```bash
source venv/bin/activate
vapid --gen
```

This creates `private_key.pem` and `public_key.pem` in the current directory.

Then set file paths in `.env`:

## Setup

From `backend/`:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

On non-Linux development machines, the Raspberry Pi-specific packages (`RPi.GPIO` and `spidev`) are skipped automatically.

## Display Setup (Waveshare 2.4" SPI)

On Raspberry Pi, install required system packages:

```bash
sudo apt update
sudo apt install -y build-essential python3-dev
```

The display app uses the bundled fonts in `backend/src/assets/`, so no separate font installation is required on the device.

Enable SPI in firmware config (required for `/dev/spidev0.0`):

```bash
CFG=/boot/firmware/config.txt; [ -f "$CFG" ] || CFG=/boot/config.txt
grep -q '^dtparam=spi=on' "$CFG" || echo 'dtparam=spi=on' | sudo tee -a "$CFG"
sudo reboot
```

Then install Python dependencies from `backend/`:

```bash
source venv/bin/activate
pip install -r requirements.txt
```

Touch button wiring used by the input service:

- Grove Touch Sensor `SIG` -> Raspberry Pi `GPIO24` (physical pin `18`)
- Grove Touch Sensor `VCC` -> Raspberry Pi `3.3V`
- Grove Touch Sensor `GND` -> Raspberry Pi `GND`
- The second Grove pin (`NC` / white wire) is unused
- Layout switching is triggered on button press for fast response; holding for 5 seconds requests system shutdown.

## Local Development

The runtime entrypoints now live under `backend/src`, so run them as `python src/...` scripts. For the API server, use `uvicorn --app-dir src`.

### 1. Run the Collector

```bash
cd backend
source venv/bin/activate
python src/collector.py
```

Optional custom settings:

```bash
python src/collector.py --db ./data.db --interval 5
```

### 2. Run the API Server

In a separate terminal:

```bash
cd backend
source venv/bin/activate
uvicorn --app-dir src server:app --reload --host 0.0.0.0 --port 8000
```

### 3. Run the Alerter

In a third terminal:

```bash
cd backend
source venv/bin/activate
python src/alerter.py
```

Optional custom settings:

```bash
python src/alerter.py --db ./data.db --poll-interval 5
```

### 4. Run the Local Display

On the Raspberry Pi with the SPI display and touch sensor connected:

```bash
cd backend
source venv/bin/activate
python src/display.py --db ./data.db --interval 5
```

### 5. Run the Local Input Service

In another terminal on the Raspberry Pi:

```bash
cd backend
sudo ./venv/bin/python src/input.py
```

### 6. Preview the Display Locally

You can render the same display layouts to PNG files on your development machine without SPI hardware.

Example with fake readings:

```bash
cd backend
source venv/bin/activate
python src/display_preview.py --co2 1750 --temperature 23.4 --humidity 46 --trend 3.8
```

This writes `display-preview-standard.png` and `display-preview-faces.png` into `backend/preview_out/`.

## Run as systemd Services (Linux / Raspberry Pi)

The repository includes:

- `ops/systemd/airqmon-collector.service`
- `ops/systemd/airqmon-web.service`
- `ops/systemd/airqmon-alerter.service`
- `ops/systemd/airqmon-display.service`
- `ops/systemd/airqmon-input.service`
- `ops/systemd/airqmon.target`
- `ops/airqmon-launch.sh`
- `ops/install_systemd.sh`

`ops/airqmon-launch.sh` is an internal wrapper used by the systemd units. You normally should not run it manually; use `systemctl` on `airqmon.target` or the individual `airqmon-*.service` units instead.

### 1. Prepare environment

```bash
cd /home/admin/airqmon/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Prepare the application env file

From repository root:

```bash
cp backend/.env.sample backend/.env
# edit backend/.env and set real VAPID values
```

The web and alerter processes still load their VAPID settings from `backend/.env`.

## Testing

From `backend/`:

```bash
source venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest
```

### 3. Install the wrapper and start everything

From repository root:

```bash
sudo bash backend/ops/install_systemd.sh --start
```

This installer:

- copies `airqmon-launch.sh` to `/usr/local/bin/airqmon-launch`
- installs all unit files plus `airqmon.target`
- writes shared runtime settings to `/etc/airqmon/airqmon.env`
- enables `airqmon.target`, which starts all five services together

For normal operation, manage the backend with `systemctl`. The launcher is still useful for low-level debugging, but it is not intended to be the routine manual entrypoint.

Default behavior:

- collector, web, alerter, and display run as the `sudo` caller (`$SUDO_USER`) when available
- input runs as `root`
- backend path comes from the checked-out repository location
- python path defaults to `backend/venv/bin/python`
- database path defaults to `backend/data.db`

To customize users, paths, or intervals during install:

```bash
sudo bash backend/ops/install_systemd.sh \
  --app-user admin \
  --input-user root \
  --python /home/admin/airqmon/backend/venv/bin/python \
  --db /home/admin/airqmon/backend/data.db \
  --app-env-file /home/admin/airqmon/backend/.env \
  --web-port 8000 \
  --poll-interval 5 \
  --start
```

After install, you can adjust the shared runtime settings in:

```bash
sudoedit /etc/airqmon/airqmon.env
sudo systemctl restart airqmon.target
```

### 4. Verify status and logs

```bash
sudo systemctl status airqmon.target
sudo systemctl status airqmon-collector.service
sudo systemctl status airqmon-web.service
sudo systemctl status airqmon-alerter.service
sudo systemctl status airqmon-display.service
sudo systemctl status airqmon-input.service
sudo journalctl -u airqmon-collector -f
sudo journalctl -u airqmon-web -f
sudo journalctl -u airqmon-alerter -f
sudo journalctl -u airqmon-display -f
sudo journalctl -u airqmon-input -f
```

## Data Storage

- Database: SQLite (`backend/data.db` by default)
- Table: `measurements`
- Columns: `id`, `ts`, `co2`, `temperature`, `humidity`

## Troubleshooting

- Service fails to start:
  - `sudo systemctl status airqmon-web.service`
  - `sudo journalctl -u airqmon-web -n 200`
- Collector not writing rows:
  - check collector logs via `journalctl`
  - verify `--db` path is writable
- Permission errors:
  - verify the generated service user exists and owns project files
  - rerun `ops/install_systemd.sh --app-user <user>` if needed
- Port conflicts on `8000`:
  - change `AIRQMON_WEB_PORT` in `/etc/airqmon/airqmon.env`
  - restart `airqmon.target`

