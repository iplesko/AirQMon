# AirQMon

AirQMon is a two-part indoor air quality monitoring system:

- `backend/`: A Python service that reads CO2, temperature, and humidity values, stores them in SQLite, and exposes a FastAPI API.
- `frontend/`: A React + TypeScript single-page app that shows the latest reading and charts historical trends.

Target hardware setup:

- Raspberry Pi Zero 2 W
- DFRobot SEN0536 (SCD41 infrared CO2 sensor)
- I2C connection via Raspberry Pi GPIO pins

## What the Applications Do

### Backend (`backend/`)
The backend contains two runtime pieces:

- `collector.py`
  - Polls the sensor on an interval (default: 10 seconds).
  - Falls back to a simulator when hardware is unavailable.
  - Writes measurements (`co2`, `temperature`, `humidity`, timestamp) to `backend/data.db`.
  - Prunes data older than 7 days.

- `alerter.py`
  - Watches newly inserted measurements in SQLite.
  - Sends ntfy notifications when CO2 is above a configurable threshold.
  - Sends a recovery notification when CO2 falls below clear threshold.
  - Persists alert state in DB so restarts avoid duplicate alerts.

- `server.py`
  - Exposes API endpoints:
    - `GET /api/latest`: latest measurement.
    - `GET /api/data`: time-range query with optional point limiting.
  - Serves built frontend static files from `frontend/dist` when present.

### Frontend (`frontend/`)
The frontend dashboard:

- Polls `GET /api/latest` and `GET /api/data` every 5 seconds.
- Shows the current CO2/temperature/humidity values.
- Renders historical line charts (CO2, temperature, humidity).
- Supports selectable time ranges and a mobile-friendly reduced-points mode.

## How It Fits Together

1. The collector continuously writes sensor readings into SQLite.
2. The API reads from SQLite and serves measurement data.
3. The frontend calls the API and visualizes the results.

## Project Layout

- `backend/` Python collector + FastAPI API + systemd units
- `frontend/` React/Vite UI
- `.gitignore` repository ignore rules

## App-Specific Setup

For installation and run instructions, see:

- [backend/README.md](backend/README.md)
- [frontend/README.md](frontend/README.md)

