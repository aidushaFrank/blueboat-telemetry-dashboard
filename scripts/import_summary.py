#!/usr/bin/env python3
"""
Compute run-level totals from the FULL GPS track in the .tlog (not the sampled
sonar pings) and write them to InfluxDB as measurement 'sonar_summary'.

These are single-value fields meant for Grafana Stat panels:
    active_time_s    - seconds from first to last valid GPS fix
    distance_m       - total path length (jitter-filtered), meters
    distance_km      - same in km
    mean_speed_ms    - distance / active_time
    voltage_start_v / voltage_end_v / voltage_drop_v - battery voltage change

Setup:
    pip install pymavlink pandas influxdb-client

Env vars (same as the other importers):
    INFLUX_ORG, INFLUX_BUCKET, INFLUX_TOKEN, INFLUX_URL

Run:
    python scripts/import_summary.py path/to/flight.tlog
"""

import os, sys
from pathlib import Path
import numpy as np
import pandas as pd
from pymavlink import mavutil
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

URL    = os.environ.get("INFLUX_URL", "http://localhost:8086")
TOKEN  = os.environ["INFLUX_TOKEN"]
ORG    = os.environ.get("INFLUX_ORG", "caltech_lab")
BUCKET = os.environ.get("INFLUX_BUCKET", "qgc_data")

MEASUREMENT = "sonar_summary"
RUN_TAG     = "sonar_2026_05_29"
JITTER_M    = 0.02  # ignore GPS hops smaller than this (noise while stationary)

tlog = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/flight.tlog")

m = mavutil.mavlink_connection(str(tlog))
gps, volts = [], []
while True:
    msg = m.recv_match(blocking=False)
    if msg is None:
        break
    t = msg.get_type()
    if t == "GLOBAL_POSITION_INT" and (msg.lat != 0 or msg.lon != 0):
        gps.append({"t": msg._timestamp, "lat": msg.lat/1e7, "lon": msg.lon/1e7})
    elif t == "SYS_STATUS" and msg.voltage_battery not in (0, 65535):
        volts.append({"t": msg._timestamp, "v": msg.voltage_battery/1000.0})

g = pd.DataFrame(gps).sort_values("t").reset_index(drop=True)
active_time_s = float(g["t"].iloc[-1] - g["t"].iloc[0])

lat = np.radians(g["lat"].values); lon = np.radians(g["lon"].values); R = 6371000.0
dlat = np.diff(lat); dlon = np.diff(lon)
a = np.sin(dlat/2)**2 + np.cos(lat[:-1])*np.cos(lat[1:])*np.sin(dlon/2)**2
seg = 2*R*np.arcsin(np.sqrt(a))
distance_m = float(seg[seg > JITTER_M].sum())

v = pd.DataFrame(volts).sort_values("t")
v_start = float(v["v"].iloc[0]); v_end = float(v["v"].iloc[-1])

fields = {
    "active_time_s": active_time_s,
    "active_time_min": active_time_s/60.0,
    "distance_m": distance_m,
    "distance_km": distance_m/1000.0,
    "mean_speed_ms": distance_m/active_time_s if active_time_s else 0.0,
    "voltage_start_v": v_start,
    "voltage_end_v": v_end,
    "voltage_drop_v": v_start - v_end,
}

client = InfluxDBClient(url=URL, token=TOKEN, org=ORG)
write_api = client.write_api(write_options=SYNCHRONOUS)
p = Point(MEASUREMENT).tag("run", RUN_TAG).time(
    pd.to_datetime(g["t"].iloc[0], unit="s", utc=True), WritePrecision.MS)
for k, val in fields.items():
    p = p.field(k, float(val))
write_api.write(bucket=BUCKET, org=ORG, record=p)
client.close()

print(f"Wrote summary -> measurement '{MEASUREMENT}', run '{RUN_TAG}':")
for k, val in fields.items():
    print(f"  {k}: {round(val, 3)}")
