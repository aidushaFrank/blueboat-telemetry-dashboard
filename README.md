# BlueBoat Telemetry Dashboard

A Docker-based telemetry dashboard for visualizing cleaned QGroundControl telemetry data from BlueBoat missions.

The project uses **InfluxDB** for time-series data storage and **Grafana** for dashboard visualization. The current version works with cleaned CSV telemetry files and sample mission data. Future development will focus on live or near-real-time telemetry ingestion.

## Current Features

The dashboard currently visualizes:

* Boat path on a map
* Mission duration
* Total distance
* Battery voltage over time
* Speed over time
* Heading over time
* Altitude over time

## Project Status

This repository contains a working prototype for telemetry review using cleaned QGroundControl data.

Current version:

* Runs locally with Docker Compose
* Starts InfluxDB and Grafana containers
* Imports cleaned telemetry CSV files into InfluxDB
* Visualizes mission data in Grafana
* Uses sample or cleaned data only

Future work:

* Add live or near-real-time telemetry ingestion
* Add cleaner mission summary statistics
* Support easier comparison between multiple runs
* Add additional sensor streams such as conductivity and temperature
* Improve documentation for team use during field deployments

## Tech Stack

* Docker
* Docker Compose
* InfluxDB 2.7
* Grafana
* Python
* QGroundControl telemetry logs
* Flux queries

## Repository Structure

```text
.
├── dashboards/                  # Grafana dashboard files
├── data/                        # Cleaned or sample telemetry CSV files
├── provisioning/                # Grafana datasource and dashboard provisioning
│   ├── dashboards/
│   └── datasources/
├── scripts/                     # Python import scripts
├── docker-compose.yml           # Docker setup for InfluxDB and Grafana
├── requirements.txt             # Python dependencies
├── .env.example                 # Example environment variables
├── .gitignore
└── README.md
```

## How It Works

The basic workflow is:

```text
QGroundControl telemetry logs
        ↓
cleaned CSV files
        ↓
Python import scripts
        ↓
InfluxDB time-series database
        ↓
Grafana dashboard
```

The map is reconstructed from GPS latitude and longitude points. Other panels use cleaned telemetry fields such as speed, heading, altitude, and battery voltage.

## Setup Instructions

### 1. Clone the repository

```bash
git clone https://github.com/YOUR-USERNAME/blueboat-telemetry-dashboard.git
cd blueboat-telemetry-dashboard
```

### 2. Create the environment file

Copy the example environment file:

```bash
cp .env.example .env
```

Then edit `.env` with your local InfluxDB settings.

Example values:

```bash
INFLUX_ORG=caltech_lab
INFLUX_BUCKET=qgc_data
INFLUX_TOKEN=change_this_token
```

The real `.env` file is ignored by Git and should not be uploaded.

### 3. Start Docker containers

```bash
docker compose up -d
```

This starts:

* InfluxDB at `http://localhost:8086`
* Grafana at `http://localhost:3000`

To stop the containers:

```bash
docker compose down
```

To fully reset the local database and Grafana volumes:

```bash
docker compose down -v
docker compose up -d
```

Use the full reset only when you are okay with deleting local InfluxDB and Grafana data.

## Python Setup

Create a virtual environment:

```bash
python3 -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Import Telemetry Data

Run the main telemetry importer:

```bash
python scripts/import_qgc_telemetry.py
```

Run the battery telemetry importer:

```bash
python scripts/import_battery_telemetry.py
```

After importing the data, open Grafana at:

```text
http://localhost:3000
```

## Main Dashboard Panels

The dashboard includes:

* Boat path map
* Battery voltage over time
* Speed over time
* Heading over time
* Altitude over time
* Mission duration
* Total distance

## Example Flux Queries

### Speed

```flux
from(bucket: "qgc_data")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "qgc_telemetry")
  |> filter(fn: (r) => r.run == "gps_track_cleaned")
  |> filter(fn: (r) => r._field == "speed_xy")
```

### Heading

```flux
from(bucket: "qgc_data")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "qgc_telemetry")
  |> filter(fn: (r) => r.run == "gps_track_cleaned")
  |> filter(fn: (r) => r._field == "heading_deg")
```

### Altitude

```flux
from(bucket: "qgc_data")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "qgc_telemetry")
  |> filter(fn: (r) => r.run == "gps_track_cleaned")
  |> filter(fn: (r) => r._field == "alt_m")
```

### Map

```flux
from(bucket: "qgc_data")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "qgc_telemetry")
  |> filter(fn: (r) => r.run == "gps_track_cleaned")
  |> filter(fn: (r) => r._field == "lat" or r._field == "lon" or r._field == "speed_xy")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["_time", "lat", "lon", "speed_xy"])
```

Grafana Geomap settings:

```text
Visualization: Geomap
Location mode: Coordinates
Latitude field: lat
Longitude field: lon
```

### Battery Voltage

```flux
from(bucket: "qgc_data")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "qgc_battery")
  |> filter(fn: (r) => r.run == "gps_track_cleaned")
  |> filter(fn: (r) => r._field == "battery_voltage_v")
  |> filter(fn: (r) => r.msg_type == "SYS_STATUS")
```

### Mission Duration

```flux
gps = from(bucket: "qgc_data")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "gps_track")
  |> filter(fn: (r) => r.track == "gps_track_cleaned")
  |> filter(fn: (r) => r._field == "lat")

first_time = gps |> first()
last_time = gps |> last()

union(tables: [first_time, last_time])
  |> keep(columns: ["_time"])
  |> sort(columns: ["_time"])
  |> elapsed(unit: 1s)
```

The output can be converted to minutes using Grafana transformations.

### Total Distance

For the current sample run, total distance was calculated separately from cleaned GPS points and displayed as a stat panel.

```flux
import "array"

array.from(rows: [
  {_time: now(), _value: 1.9326}
])
```

## Notes and Limitations

* This dashboard is based on cleaned QGroundControl telemetry data.
* The current version is not real-time yet.
* The map is reconstructed from GPS data.
* `alt_m` represents autopilot/GPS reported altitude, not sonar depth.
* Battery data depends on the correct telemetry log containing battery messages.
* This repository should not include private tokens, raw field logs, or sensitive deployment data.

## Future Development

A separate branch can be used for real-time dashboard development:

```bash
git checkout -b realtime-dashboard
```

Once the real-time version is stable, it can be reviewed and merged into the main branch.
