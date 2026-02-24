# Backend

## Overview

The backend has two processes:

- `collector.py`: reads sensor values (CO2, temperature, humidity) and stores them in SQLite.
- `server.py`: exposes REST endpoints and optionally serves the built frontend from `../frontend/dist`.
- `alerter.py`: watches new measurements in SQLite and sends ntfy alerts when CO2 is high.

Tested hardware setup:

- Raspberry Pi Zero 2 W
- DFRobot SEN0536 (SCD41 infrared CO2 sensor)
- I2C connection via Raspberry Pi GPIO pins

## Components

### Data Collector (`collector.py`)

- Reads from SCD4X (`scd4x` package) when available.
- Falls back to simulated values if sensor/driver is unavailable.
- Writes to `data.db` (default) every `--interval` seconds (default: `10`).
- Prunes data older than 7 days once per hour.

CLI options:

- `--db`: SQLite file path (default: `backend/data.db`)
- `--interval`: collection interval in seconds (default: `10.0`)

### API Server (`server.py`)

Endpoints:

- `GET /api/latest`: latest measurement row.
- `GET /api/data?start=<unix>&end=<unix>&points=<n>`:
  - `start`/`end` are optional UNIX timestamps.
  - Defaults to the last 24 hours when omitted.
  - `points` defaults to `500`, max `10000`, and downsamples evenly.
- `GET /api/config`: returns alert config (`ntfy_topic`, `co2_high`, `co2_clear`, `cooldown_seconds`).
- `PUT /api/config`: replaces alert config values (`ntfy_topic`, `co2_high`, `co2_clear`, `cooldown_seconds`).

Static serving:

- If `frontend/dist` exists, the backend serves it at `/`.
- If it does not exist, API routes still work, but no frontend static files are served.

### Alert Worker (`alerter.py`)

- Polls the same SQLite DB for newly inserted measurements.
- Sends ntfy notifications when CO2 crosses a high threshold.
- Sends a recovery notification when CO2 returns below a clear threshold.
- Persists alert state (`last_seen_id`, `in_alert`, `last_alert_ts`) in DB, so restarts do not spam.

CLI options (selected):

- `--db`: SQLite file path (default: `backend/data.db`)
- `--poll-interval`: seconds between DB polls (default: `5`)

## Requirements

- Python 3
- `pip`
- Linux systemd (only if running as services)

Install Python dependencies from `requirements.txt`:

- `fastapi`
- `uvicorn`
- `scd4x`

## Setup

From `backend/`:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Local Development

### 1. Run the Collector

```bash
cd backend
source venv/bin/activate
python collector.py
```

Optional custom settings:

```bash
python collector.py --db ./data.db --interval 5
```

### 2. Run the API Server

In a separate terminal:

```bash
cd backend
source venv/bin/activate
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

### 3. Run the Alerter

In a third terminal:

```bash
cd backend
source venv/bin/activate
python alerter.py
```

Optional custom settings:

```bash
python alerter.py --db ./data.db --poll-interval 5
```

## Run as systemd Services (Linux / Raspberry Pi)

The repository includes:

- `airqmon-collector.service`
- `airqmon-web.service`
- `airqmon-alerter.service`

### 1. Prepare environment

```bash
cd /home/admin/airqmon/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Review service files before install

The shipped units assume:

- user: `admin`
- working directory: `/home/admin/airqmon/backend`
- python binary: `/home/admin/airqmon/backend/venv/bin/python`

If your setup differs, edit both service files first.

### 3. Install and start services

From repository root:

```bash
sudo cp backend/airqmon-collector.service /etc/systemd/system/airqmon-collector.service
sudo cp backend/airqmon-web.service /etc/systemd/system/airqmon-web.service
sudo cp backend/airqmon-alerter.service /etc/systemd/system/airqmon-alerter.service
sudo systemctl daemon-reload
```

Start and enable services:

```bash
sudo systemctl enable --now airqmon-collector.service
sudo systemctl enable --now airqmon-web.service
sudo systemctl enable --now airqmon-alerter.service
```

### 4. Verify status and logs

```bash
sudo systemctl status airqmon-collector.service
sudo systemctl status airqmon-web.service
sudo systemctl status airqmon-alerter.service
sudo journalctl -u airqmon-collector -f
sudo journalctl -u airqmon-web -f
sudo journalctl -u airqmon-alerter -f
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
  - verify service `User=` exists and owns project files
- Port conflicts on `8000`:
  - change port in `airqmon-web.service` `ExecStart`

