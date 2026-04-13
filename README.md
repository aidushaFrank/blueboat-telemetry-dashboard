QGC telemetry dashboard notes


folder

WSL path:
/mnt/c/Users/kudai/OneDrive/Desktop/caltech/qgc-telemetry-dashboard

Windows path:
C:\Users\kudai\OneDrive\Desktop\caltech\qgc-telemetry-dashboard
main idea


Use cleaned QGC telemetry CSV.

Import into Influx.

Open in Grafana.

Show map + speed + heading + relative altitude.



go to repo
cd /mnt/c/Users/kudai/OneDrive/Desktop/caltech/qgc-telemetry-dashboard


docker commands
start in background:

docker compose up -d

see logs if needed:
docker compose logs -f

stop:
docker compose down

full reset if token / setup got messed up:

docker compose down -v
docker compose up -d

open pages
InfluxDB: http://localhost:8086

Grafana: http://localhost:3000



If needed:

cp .env.example .env
Important: same token in both places.

DOCKER_INFLUXDB_INIT_ADMIN_TOKEN

INFLUX_TOKEN


If I change token after containers were already created, I probably need:

docker compose down -v
docker compose up -d
venv


create if needed:

python3 -m venv .venv

turn on:
source .venv/bin/activate

turn off:

deactivate if missing:

sudo apt update
sudo apt install python3-venv -y
install packages inside venv:

python -m pip install -r requirements.txt
env vars for importer


Python importer does not automatically read Docker stuff the way I want, so before running importer I need these in the same terminal:

export INFLUX_ORG=caltech_lab
export INFLUX_BUCKET=qgc_data
export INFLUX_TOKEN=DLJLkCA1ZqRLtFplPcjuPEVPC_67khKtiJPnHv8kRMpOeUEyJS11VxEldzKd1VIfJGcVKoJqjEz8OQFGOfxD2Q==
quick checks:

echo $INFLUX_ORG
echo $INFLUX_BUCKET
echo $INFLUX_TOKEN=DLJLkCA1ZqRLtFplPcjuPEVPC_67khKtiJPnHv8kRMpOeUEyJS11VxEldzKd1VIfJGcVKoJqjEz8OQFGOfxD2Q==
run importer


with venv on and env vars set:

python scripts/import_qgc_telemetry.py




if still weird and repo is fresh, reset:

docker compose down -v
docker compose up -d
then export vars again and rerun importer.



what the columns mean


lat / lon
GPS coordinates in decimal degrees

use for map



heading_deg
compass direction

0 = north, 90 = east, 180 = south, 270 = west

best as line chart over time



speed_xy
cleaned formula is:

sqrt(vx^2 + vy^2) / 100

best as line chart over time



alt_m
meters

came from GLOBAL_POSITION_INT.alt


relative_alt_m
meters

relative to starting / home reference

probably more useful to show than alt_m



best panels



Boat Path map

Speed Over Time

Heading Over Time

Relative Altitude Over Time



grafana queries


speed
from(bucket: "qgc_data")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "qgc_telemetry")
  |> filter(fn: (r) => r.run == "gps_track_cleaned")
  |> filter(fn: (r) => r._field == "speed_xy")
heading
from(bucket: "qgc_data")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "qgc_telemetry")
  |> filter(fn: (r) => r.run == "gps_track_cleaned")
  |> filter(fn: (r) => r._field == "heading_deg")
alt_m
from(bucket: "qgc_data")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "qgc_telemetry")
  |> filter(fn: (r) => r.run == "gps_track_cleaned")
  |> filter(fn: (r) => r._field == "alt_m")
relative_alt_m
from(bucket: "qgc_data")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "qgc_telemetry")
  |> filter(fn: (r) => r.run == "gps_track_cleaned")
  |> filter(fn: (r) => r._field == "relative_alt_m")
map
from(bucket: "qgc_data")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "qgc_telemetry")
  |> filter(fn: (r) => r.run == "gps_track_cleaned")
  |> filter(fn: (r) => r._field == "lat" or r._field == "lon" or r._field == "speed_xy")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["_time", "lat", "lon", "speed_xy"])
Geomap settings:

Visualization = Geomap

Location mode = Coords

Latitude field = lat

Longitude field = lon




Easy fix while building panels:

|> range(start: 0)


This dashboard is from cleaned QGroundControl telemetry.

Map is reconstructed from GPS.

Time series show speed, heading, and vertical position over time.

alt_m is autopilot / GPS reported altitude, not sonar bathymetry depth.



quick workflow reminder


normal session
cd /mnt/c/Users/kudai/OneDrive/Desktop/caltech/qgc-telemetry-dashboard
source .venv/bin/activate
export INFLUX_ORG=caltech_lab
export INFLUX_BUCKET=qgc_data
export INFLUX_TOKEN=my_exact_token_here
docker compose up -d
after changing csv
cd /mnt/c/Users/kudai/OneDrive/Desktop/caltech/qgc-telemetry-dashboard
source .venv/bin/activate
export INFLUX_ORG=caltech_lab
export INFLUX_BUCKET=qgc_data
export INFLUX_TOKEN=my_exact_token_here
python scripts/import_qgc_telemetry.py
finish
docker compose down
deactivate
