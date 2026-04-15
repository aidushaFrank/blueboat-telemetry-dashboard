# qgc telemetry dashboard

this repo is for my grafana + influxdb dashboard for cleaned qgroundcontrol telemetry.

right now the dashboard shows:

* boat path on map
* mission duration
* total distance
* battery voltage over time
* speed over time
* heading over time
* altitude over time

## project folder

wsl path:
`/mnt/c/Users/kudai/OneDrive/Desktop/caltech/qgc-telemetry-dashboard`

windows path:
`C:\Users\kudai\OneDrive\Desktop\caltech\qgc-telemetry-dashboard`

## basic idea

use cleaned qgc telemetry csv files, import them into influxdb, and visualize the run in grafana.

## start / stop

go to repo:

```bash
cd /mnt/c/Users/kudai/OneDrive/Desktop/caltech/qgc-telemetry-dashboard
```

start docker:

```bash
docker compose up -d
```

stop docker:

```bash
docker compose down
```

full reset if setup gets weird:

```bash
docker compose down -v
docker compose up -d
```

open pages:

* influxdb: `http://localhost:8086`
* grafana: `http://localhost:3000`

## python setup

create venv if needed:

```bash
python3 -m venv .venv
```

turn on:

```bash
source .venv/bin/activate
```

install packages:

```bash
python -m pip install -r requirements.txt
```

## env vars

before running importers:

```bash
export INFLUX_ORG=caltech_lab
export INFLUX_BUCKET=qgc_data
export INFLUX_TOKEN=change
```

## run importers

main telemetry importer:

```bash
python scripts/import_qgc_telemetry.py
```

battery importer:

```bash
python scripts/import_battery_telemetry.py
```

## main panels

* boat path
* battery voltage
* speed
* heading
* altitude
* mission duration
* total distance

## useful queries

### speed

```flux
from(bucket: "qgc_data")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "qgc_telemetry")
  |> filter(fn: (r) => r.run == "gps_track_cleaned")
  |> filter(fn: (r) => r._field == "speed_xy")
```

### heading

```flux
from(bucket: "qgc_data")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "qgc_telemetry")
  |> filter(fn: (r) => r.run == "gps_track_cleaned")
  |> filter(fn: (r) => r._field == "heading_deg")
```

### altitude

```flux
from(bucket: "qgc_data")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "qgc_telemetry")
  |> filter(fn: (r) => r.run == "gps_track_cleaned")
  |> filter(fn: (r) => r._field == "alt_m")
```

### map

```flux
from(bucket: "qgc_data")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "qgc_telemetry")
  |> filter(fn: (r) => r.run == "gps_track_cleaned")
  |> filter(fn: (r) => r._field == "lat" or r._field == "lon" or r._field == "speed_xy")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["_time", "lat", "lon", "speed_xy"])
```

geomap settings:

* visualization = geomap
* location mode = coords
* latitude field = lat
* longitude field = lon

### battery voltage

```flux
from(bucket: "qgc_data")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "qgc_battery")
  |> filter(fn: (r) => r.run == "gps_track_cleaned")
  |> filter(fn: (r) => r._field == "battery_voltage_v")
  |> filter(fn: (r) => r.msg_type == "SYS_STATUS")
```

### mission duration

this is the version that worked for me, then i converted it to minutes in grafana transformations:

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

### total distance

for total distance i calculated it separately from the cleaned gps points and used `1.93 km`

for the stat panel:

```flux
import "array"

array.from(rows: [
  {_time: now(), _value: 1.9326}
])
```

## notes

* this dashboard is from cleaned qgroundcontrol telemetry
* map is reconstructed from gps
* `alt_m` is autopilot / gps reported altitude, not sonar depth
* battery was missing at first because i used the wrong tlog
* once i found the correct tlog, battery voltage over time worked

## current status

right now this is a working prototype for telemetry review.

next things i could add later:

* cleaner battery summary stats
* live / near-real-time ingestion
* more mission summary values
* easier comparison between runs
