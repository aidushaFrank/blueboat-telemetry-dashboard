#!/usr/bin/env python3
"""
Import sonar+telemetry merged CSV into the existing qgc_data bucket (InfluxDB 2.x).
Matches the conventions of the existing importers (run tag, measurement, env vars).

Setup once:
    pip install influxdb-client pandas

Env vars (same pattern as your other importers):
    export INFLUX_ORG=caltech_lab
    export INFLUX_BUCKET=qgc_data
    export INFLUX_TOKEN=your_real_token
    export INFLUX_URL=http://localhost:8086      # or http://influxdb:8086 inside docker

Layout (matches the other importers):
    <repo>/scripts/import_sonar.py          <- this file
    <repo>/data/telemetry_sonar_merged.csv  <- the CSV

Run from anywhere (path resolves relative to the script):
    python scripts/import_sonar.py
"""

import os
from pathlib import Path
import pandas as pd
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# ----------------------- CONFIG -----------------------
# Same convention as the other importers: data/ lives one level up from scripts/.
# Place the CSV at <repo>/data/telemetry_sonar_merged.csv and this script at
# <repo>/scripts/import_sonar.py. Override with SONAR_CSV env var if needed.
DATA_FILE   = Path(__file__).resolve().parent.parent / "data" / "telemetry_sonar_merged.csv"
CSV_PATH    = os.environ.get("SONAR_CSV", str(DATA_FILE))
URL         = os.environ.get("INFLUX_URL", "http://localhost:8086")
TOKEN       = os.environ["INFLUX_TOKEN"]
ORG         = os.environ.get("INFLUX_ORG", "caltech_lab")
BUCKET      = os.environ.get("INFLUX_BUCKET", "qgc_data")

MEASUREMENT = "sonar_view"          # parallel to qgc_telemetry / qgc_battery
RUN_TAG     = "sonar_2026_05_29"    # single run for all 4 windows
TIME_COLUMN = "datetime"            # UTC; Influx stores UTC, display PDT in Grafana
# ------------------------------------------------------

# Map: original CSV column -> clean Influx field name. Only these are written.
FIELD_MAP = {
    "altitude (m)":                 "depth_m",          # sonar depth (negative-down)
    "northing (local m)":           "northing_m",
    "easting (local m)":            "easting_m",
    "ping number":                  "ping_number",
    "elapsed (s)":                  "elapsed_s",
    "GLOBAL_POSITION_INT.lat":      "lat",              # boat GPS, decimal degrees
    "GLOBAL_POSITION_INT.lon":      "lon",              # boat GPS, decimal degrees
    "beam_lat":                     "beam_lat",         # per-beam georeferenced position
    "beam_lon":                     "beam_lon",
    "GLOBAL_POSITION_INT.relative_alt": "gps_rel_alt_m",
    "VFR_HUD.groundspeed":          "groundspeed_ms",
    "VFR_HUD.heading":              "heading_deg",
    "ATTITUDE.roll":                "roll_rad",
    "ATTITUDE.pitch":               "pitch_rad",
    "ATTITUDE.yaw":                 "yaw_rad",
    "VFR_HUD.climb":                "climb_ms",
    "VFR_HUD.alt":                  "vfr_alt_m",
    "LOCAL_POSITION_NED.x":         "ned_x_m",
    "LOCAL_POSITION_NED.y":         "ned_y_m",
    "LOCAL_POSITION_NED.z":         "ned_z_m",
    "RANGEFINDER.distance":         "rangefinder_m",
    "SYS_STATUS.voltage_battery":   "battery_voltage_mv",
    "BATTERY_STATUS.current_battery":   "battery_current_ca",
    "BATTERY_STATUS.battery_remaining": "battery_remaining_pct",
}

# Keep the source filename as a tag so the 4 windows stay distinguishable.
SOURCE_TAG_COLUMN = "source_file"

df = pd.read_csv(CSV_PATH)
df[TIME_COLUMN] = pd.to_datetime(df[TIME_COLUMN], utc=True, format="ISO8601")

client = InfluxDBClient(url=URL, token=TOKEN, org=ORG)
write_api = client.write_api(write_options=SYNCHRONOUS)

points = []
for _, row in df.iterrows():
    p = Point(MEASUREMENT).time(row[TIME_COLUMN], WritePrecision.MS)
    p = p.tag("run", RUN_TAG)
    if SOURCE_TAG_COLUMN in df.columns and pd.notna(row[SOURCE_TAG_COLUMN]):
        p = p.tag("source_file", str(row[SOURCE_TAG_COLUMN]))
    wrote_field = False
    for src, dst in FIELD_MAP.items():
        if src in df.columns:
            v = row[src]
            if pd.notna(v):
                try:
                    p = p.field(dst, float(v))
                    wrote_field = True
                except (ValueError, TypeError):
                    pass
    if wrote_field:
        points.append(p)

write_api.write(bucket=BUCKET, org=ORG, record=points)
client.close()
print(f"Wrote {len(points)} points -> bucket '{BUCKET}', measurement '{MEASUREMENT}', run '{RUN_TAG}'.")
