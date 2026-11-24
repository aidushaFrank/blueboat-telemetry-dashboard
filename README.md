# BlueBoat Telemetry Dashboard

A Docker-based telemetry dashboard for visualizing cleaned QGroundControl and sonar telemetry data.

## Prerequisites

- Docker Desktop (Windows/macOS) or Docker Engine + Docker Compose (Linux)
- Python 3.10 or newer
- Git

Verify Docker:

```bash
docker --version
docker compose version
```

## 1. Clone the repository

```bash
git clone https://github.com/aidushaFrank/blueboat-telemetry-dashboard.git
cd blueboat-telemetry-dashboard
```

## 2. Create the environment file

macOS/Linux:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Open `.env` and replace every `change` value. Keep the organization and bucket values consistent across Docker, Grafana, and the Python importers.

The `.env` file is intentionally ignored by Git and must never be committed.

## 3. Start Docker

Start Docker Desktop, then run:

```bash
docker compose up -d
```

Open:

- InfluxDB: http://localhost:8086
- Grafana: http://localhost:3000

Grafana and InfluxDB credentials come from `.env`. If you change the InfluxDB token after the first startup, reset the Docker volumes before restarting:

```bash
docker compose down -v
docker compose up -d
```

To stop containers without deleting data:

```bash
docker compose down
```

## 4. Set up Python

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Windows PowerShell

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks the virtual-environment activation script, enable scripts for the current process:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

## 5. Import telemetry

Python must be able to read the values in `.env`. Export or load `.env` into the active shell before running scripts.

macOS/Linux:

```bash
set -a
source .env
set +a
python scripts/import_qgc_telemetry.py
python scripts/import_battery_telemetry.py
```

Windows PowerShell:

```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^([^#][^=]*)=(.*)$') {
    [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), 'Process')
  }
}
python scripts/import_qgc_telemetry.py
python scripts/import_battery_telemetry.py
```

Refresh Grafana after importing. The files in `data/` are cleaned or sample data only.

## Repository layout

```text
.
├── data/                        # Cleaned or sample telemetry CSV files
├── provisioning/
│   ├── dashboards/              # Grafana provisioning configuration
│   └── datasources/             # InfluxDB datasource configuration
├── scripts/                     # Python import and replay scripts
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Available scripts

- `scripts/import_qgc_telemetry.py` — imports cleaned GPS/telemetry CSV data
- `scripts/import_battery_telemetry.py` — imports battery telemetry
- `scripts/import_sonar.py` — imports sonar data
- `scripts/import_merged_sonar_gps_2026_06_22.py` — imports merged sonar/GPS data
- `scripts/import_tlog_telemetry.py` — imports telemetry logs
- `scripts/replay_mission_live.py` — replay helper
- `scripts/replay_merged_sonar_live.py` — replay helper

## Troubleshooting

- If port `8086` or `3000` is already used, stop the other service or change the host port in `docker-compose.yml`.
- If Grafana cannot see InfluxDB, confirm that the organization and bucket in `provisioning/datasources/influxdb.yml` match `.env`.
- If imports fail with missing environment variables, confirm `.env` is loaded in the terminal.
- Use `docker compose logs` to inspect container startup problems.
- Use `docker compose down -v` only when you intentionally want to erase all local InfluxDB and Grafana data.

## Data and security

Do not commit real tokens, `.env`, raw field logs, private deployment data, or `.tlog` files. The repository contains cleaned/sample mission data only.
