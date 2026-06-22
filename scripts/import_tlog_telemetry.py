#!/usr/bin/env python3
"""
Import continuous QGroundControl MAVLink telemetry directly from a .tlog file
into InfluxDB 2.x.

The script keeps full-rate telemetry separate from sonar-linked data:

    sonar_view          -> sonar/bathymetry data
    qgc_full_telemetry  -> continuous boat telemetry from the .tlog

Example:
    python scripts/import_tlog_telemetry.py \
        "data/2026-05-29 10-47-53 (3).tlog" \
        --run sonar_2026_05_29

Required environment variables:
    INFLUX_TOKEN

Optional environment variables:
    INFLUX_URL       default: http://localhost:8086
    INFLUX_ORG       default: caltech_lab
    INFLUX_BUCKET    default: qgc_data

Dependencies:
    pip install pymavlink influxdb-client
"""

from __future__ import annotations

import argparse
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from pymavlink import mavutil


DEFAULT_MEASUREMENT = "qgc_full_telemetry"
DEFAULT_BATCH_SIZE = 5_000


def valid_number(value: Any) -> bool:
    """Return True only for finite numeric values."""
    if value is None:
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def add_field(point: Point, name: str, value: Any, scale: float = 1.0) -> bool:
    """Add a normalized numeric field when the MAVLink value is valid."""
    if not valid_number(value):
        return False
    point.field(name, float(value) * scale)
    return True


def point_from_message(
    msg: Any,
    measurement: str,
    run_name: str,
) -> Point | None:
    """
    Convert selected MAVLink messages into normalized InfluxDB fields.

    Units written to InfluxDB:
      - latitude/longitude: decimal degrees
      - speed: m/s
      - heading/direction: degrees
      - voltage: volts
      - current: amps
      - attitude: radians
      - distance/altitude: meters
      - consumed charge: mAh
      - consumed energy: hJ (MAVLink BATTERY_STATUS native unit)
    """
    msg_type = msg.get_type()
    timestamp = getattr(msg, "_timestamp", None)

    if not valid_number(timestamp):
        return None

    point = (
        Point(measurement)
        .tag("run", run_name)
        .tag("source", "qgroundcontrol_tlog")
        .tag("msg_type", msg_type)
        .time(datetime.fromtimestamp(float(timestamp), tz=timezone.utc), WritePrecision.NS)
    )
    wrote = False

    if msg_type == "GLOBAL_POSITION_INT":
        if getattr(msg, "lat", 0) != 0 or getattr(msg, "lon", 0) != 0:
            wrote |= add_field(point, "lat", getattr(msg, "lat", None), 1e-7)
            wrote |= add_field(point, "lon", getattr(msg, "lon", None), 1e-7)

        wrote |= add_field(point, "alt_m", getattr(msg, "alt", None), 1e-3)
        wrote |= add_field(
            point, "relative_alt_m", getattr(msg, "relative_alt", None), 1e-3
        )
        wrote |= add_field(point, "velocity_north_ms", getattr(msg, "vx", None), 1e-2)
        wrote |= add_field(point, "velocity_east_ms", getattr(msg, "vy", None), 1e-2)
        wrote |= add_field(point, "velocity_down_ms", getattr(msg, "vz", None), 1e-2)

        hdg = getattr(msg, "hdg", None)
        if hdg not in (None, 65535):
            wrote |= add_field(point, "heading_deg", hdg, 1e-2)

        vx = getattr(msg, "vx", None)
        vy = getattr(msg, "vy", None)
        if valid_number(vx) and valid_number(vy):
            groundspeed = math.hypot(float(vx), float(vy)) / 100.0
            wrote |= add_field(point, "groundspeed_from_velocity_ms", groundspeed)

    elif msg_type == "VFR_HUD":
        wrote |= add_field(point, "groundspeed_ms", getattr(msg, "groundspeed", None))
        wrote |= add_field(point, "airspeed_ms", getattr(msg, "airspeed", None))
        wrote |= add_field(point, "heading_deg", getattr(msg, "heading", None))
        wrote |= add_field(point, "throttle_pct", getattr(msg, "throttle", None))
        wrote |= add_field(point, "vfr_alt_m", getattr(msg, "alt", None))
        wrote |= add_field(point, "climb_ms", getattr(msg, "climb", None))

    elif msg_type == "ATTITUDE":
        wrote |= add_field(point, "roll_rad", getattr(msg, "roll", None))
        wrote |= add_field(point, "pitch_rad", getattr(msg, "pitch", None))
        wrote |= add_field(point, "yaw_rad", getattr(msg, "yaw", None))
        wrote |= add_field(point, "rollspeed_rad_s", getattr(msg, "rollspeed", None))
        wrote |= add_field(point, "pitchspeed_rad_s", getattr(msg, "pitchspeed", None))
        wrote |= add_field(point, "yawspeed_rad_s", getattr(msg, "yawspeed", None))

    elif msg_type == "SYS_STATUS":
        voltage = getattr(msg, "voltage_battery", None)
        if voltage not in (None, 0, 65535):
            wrote |= add_field(point, "battery_voltage_v", voltage, 1e-3)

        current = getattr(msg, "current_battery", None)
        if current not in (None, -1):
            wrote |= add_field(point, "battery_current_a", current, 1e-2)

        remaining = getattr(msg, "battery_remaining", None)
        if remaining not in (None, -1):
            wrote |= add_field(point, "battery_remaining_pct", remaining)

        wrote |= add_field(point, "load_pct", getattr(msg, "load", None), 1e-1)
        wrote |= add_field(point, "drop_rate_comm_pct", getattr(msg, "drop_rate_comm", None), 1e-2)
        wrote |= add_field(point, "errors_comm", getattr(msg, "errors_comm", None))

    elif msg_type == "BATTERY_STATUS":
        voltage_values = getattr(msg, "voltages", None)
        if voltage_values:
            valid_cells = [
                float(v) / 1000.0
                for v in voltage_values
                if v not in (0, 65535) and valid_number(v)
            ]
            if valid_cells:
                wrote |= add_field(point, "battery_pack_voltage_v", sum(valid_cells))
                wrote |= add_field(point, "battery_cell_min_v", min(valid_cells))
                wrote |= add_field(point, "battery_cell_max_v", max(valid_cells))

        current = getattr(msg, "current_battery", None)
        if current not in (None, -1):
            wrote |= add_field(point, "battery_current_a", current, 1e-2)

        consumed = getattr(msg, "current_consumed", None)
        if consumed not in (None, -1):
            wrote |= add_field(point, "current_consumed_mah", consumed)

        energy = getattr(msg, "energy_consumed", None)
        if energy not in (None, -1):
            wrote |= add_field(point, "energy_consumed_hj", energy)

        remaining = getattr(msg, "battery_remaining", None)
        if remaining not in (None, -1):
            wrote |= add_field(point, "battery_remaining_pct", remaining)

        temperature = getattr(msg, "temperature", None)
        if temperature not in (None, 32767):
            wrote |= add_field(point, "battery_temperature_c", temperature, 1e-2)

    elif msg_type == "GPS_RAW_INT":
        fix_type = getattr(msg, "fix_type", None)
        if valid_number(fix_type):
            point.field("gps_fix_type", int(fix_type))
            wrote = True

        satellites = getattr(msg, "satellites_visible", None)
        if satellites not in (None, 255) and valid_number(satellites):
            point.field("satellites_visible", int(satellites))
            wrote = True

        eph = getattr(msg, "eph", None)
        if eph not in (None, 65535):
            wrote |= add_field(point, "gps_hdop", eph, 1e-2)

        epv = getattr(msg, "epv", None)
        if epv not in (None, 65535):
            wrote |= add_field(point, "gps_vdop", epv, 1e-2)

        if getattr(msg, "lat", 0) != 0 or getattr(msg, "lon", 0) != 0:
            wrote |= add_field(point, "gps_raw_lat", getattr(msg, "lat", None), 1e-7)
            wrote |= add_field(point, "gps_raw_lon", getattr(msg, "lon", None), 1e-7)

    elif msg_type == "WIND":
        wrote |= add_field(point, "wind_direction_deg", getattr(msg, "direction", None))
        wrote |= add_field(point, "wind_speed_ms", getattr(msg, "speed", None))
        wrote |= add_field(point, "wind_vertical_speed_ms", getattr(msg, "speed_z", None))

    elif msg_type == "RANGEFINDER":
        wrote |= add_field(point, "rangefinder_m", getattr(msg, "distance", None))
        wrote |= add_field(point, "rangefinder_voltage_v", getattr(msg, "voltage", None))

    elif msg_type == "MISSION_CURRENT":
        seq = getattr(msg, "seq", None)
        if valid_number(seq):
            point.field("mission_seq", int(seq))
            wrote = True

        total = getattr(msg, "total", None)
        if valid_number(total):
            point.field("mission_total", int(total))
            wrote = True

        state = getattr(msg, "mission_state", None)
        if valid_number(state):
            point.field("mission_state", int(state))
            wrote = True

    return point if wrote else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import selected continuous MAVLink telemetry from a QGC .tlog."
    )
    parser.add_argument("tlog", type=Path, help="Path to the input .tlog file")
    parser.add_argument(
        "--run",
        required=True,
        help="Run tag used by Grafana, for example sonar_2026_05_29",
    )
    parser.add_argument(
        "--measurement",
        default=DEFAULT_MEASUREMENT,
        help=f"InfluxDB measurement name (default: {DEFAULT_MEASUREMENT})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Number of points per InfluxDB write (default: {DEFAULT_BATCH_SIZE})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.tlog.exists():
        raise FileNotFoundError(f"TLOG file not found: {args.tlog}")

    influx_url = os.environ.get("INFLUX_URL", "http://localhost:8086")
    influx_org = os.environ.get("INFLUX_ORG", "caltech_lab")
    influx_bucket = os.environ.get("INFLUX_BUCKET", "qgc_data")
    influx_token = os.environ.get("INFLUX_TOKEN")

    if not influx_token:
        raise RuntimeError(
            "INFLUX_TOKEN is not set. Load your .env values before running the importer."
        )

    connection = mavutil.mavlink_connection(str(args.tlog))

    processed = 0
    written = 0
    counts: dict[str, int] = {}
    batch: list[Point] = []

    with InfluxDBClient(
        url=influx_url,
        token=influx_token,
        org=influx_org,
        timeout=60_000,
    ) as client:
        write_api = client.write_api(write_options=SYNCHRONOUS)

        while True:
            msg = connection.recv_match(blocking=False)
            if msg is None:
                break

            processed += 1
            msg_type = msg.get_type()

            if msg_type == "BAD_DATA":
                continue

            point = point_from_message(msg, args.measurement, args.run)
            if point is None:
                continue

            batch.append(point)
            counts[msg_type] = counts.get(msg_type, 0) + 1

            if len(batch) >= args.batch_size:
                write_api.write(
                    bucket=influx_bucket,
                    org=influx_org,
                    record=batch,
                )
                written += len(batch)
                print(f"Wrote {written:,} points...", flush=True)
                batch.clear()

        if batch:
            write_api.write(
                bucket=influx_bucket,
                org=influx_org,
                record=batch,
            )
            written += len(batch)

    print()
    print("Import complete")
    print(f"  File:        {args.tlog}")
    print(f"  Bucket:      {influx_bucket}")
    print(f"  Measurement: {args.measurement}")
    print(f"  Run tag:     {args.run}")
    print(f"  Messages read: {processed:,}")
    print(f"  Points written: {written:,}")
    print("  Imported message types:")
    for msg_type, count in sorted(counts.items()):
        print(f"    {msg_type}: {count:,}")


if __name__ == "__main__":
    main()
