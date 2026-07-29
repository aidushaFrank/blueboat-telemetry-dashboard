#!/usr/bin/env python3
"""
Replay a historical BlueBoat mission so Grafana looks live.

Inputs:
  - QGroundControl .tlog (continuous telemetry)
  - Optional merged sonar CSV (bathymetry/depth windows)

The script preserves the original order and timing, but shifts timestamps to now.
Use --speed to replay faster than real time.

Example:
    python scripts/replay_mission_live.py \
      "data/2026-05-29 10-47-53 (3).tlog" \
      --sonar-csv "data/telemetry_sonar_merged.csv" \
      --speed 20 \
      --run live_replay

Required environment variable:
    INFLUX_TOKEN

Optional environment variables:
    INFLUX_URL       default: http://localhost:8086
    INFLUX_ORG       default: caltech_lab
    INFLUX_BUCKET    default: qgc_data

Dependencies:
    pip install pymavlink pandas influxdb-client
"""

from __future__ import annotations

import argparse
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from pymavlink import mavutil


TELEMETRY_MEASUREMENT = "qgc_full_telemetry"
SONAR_MEASUREMENT = "sonar_view"

SUPPORTED_TYPES = {
    "GLOBAL_POSITION_INT",
    "VFR_HUD",
    "ATTITUDE",
    "SYS_STATUS",
    "BATTERY_STATUS",
    "GPS_RAW_INT",
    "WIND",
    "RANGEFINDER",
    "MISSION_CURRENT",
}

SONAR_FIELD_MAP = {
    "altitude (m)": "depth_m",
    "northing (local m)": "northing_m",
    "easting (local m)": "easting_m",
    "ping number": "ping_number",
    "elapsed (s)": "elapsed_s",
    "GLOBAL_POSITION_INT.lat": "lat",
    "GLOBAL_POSITION_INT.lon": "lon",
    "beam_lat": "beam_lat",
    "beam_lon": "beam_lon",
    "GLOBAL_POSITION_INT.relative_alt": "gps_rel_alt_m",
    "VFR_HUD.groundspeed": "groundspeed_ms",
    "VFR_HUD.heading": "heading_deg",
    "ATTITUDE.roll": "roll_rad",
    "ATTITUDE.pitch": "pitch_rad",
    "ATTITUDE.yaw": "yaw_rad",
    "VFR_HUD.climb": "climb_ms",
    "VFR_HUD.alt": "vfr_alt_m",
    "LOCAL_POSITION_NED.x": "ned_x_m",
    "LOCAL_POSITION_NED.y": "ned_y_m",
    "LOCAL_POSITION_NED.z": "ned_z_m",
    "RANGEFINDER.distance": "rangefinder_m",
    "SYS_STATUS.voltage_battery": "battery_voltage_mv",
    "BATTERY_STATUS.current_battery": "battery_current_ca",
    "BATTERY_STATUS.battery_remaining": "battery_remaining_pct",
}


@dataclass
class ReplayEvent:
    original_time: float
    source: str
    payload: Any


def valid_number(value: Any) -> bool:
    if value is None:
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def add_field(point: Point, name: str, value: Any, scale: float = 1.0) -> bool:
    if not valid_number(value):
        return False
    point.field(name, float(value) * scale)
    return True


def telemetry_point(
    msg: Any,
    replay_time: datetime,
    run_name: str,
) -> Point | None:
    msg_type = msg.get_type()

    point = (
        Point(TELEMETRY_MEASUREMENT)
        .tag("run", run_name)
        .tag("source", "qgroundcontrol_tlog_replay")
        .tag("msg_type", msg_type)
        .time(replay_time, WritePrecision.NS)
    )
    wrote = False

    if msg_type == "GLOBAL_POSITION_INT":
        lat = getattr(msg, "lat", None)
        lon = getattr(msg, "lon", None)
        if lat not in (None, 0) or lon not in (None, 0):
            wrote |= add_field(point, "lat", lat, 1e-7)
            wrote |= add_field(point, "lon", lon, 1e-7)

        wrote |= add_field(point, "alt_m", getattr(msg, "alt", None), 1e-3)
        wrote |= add_field(point, "relative_alt_m", getattr(msg, "relative_alt", None), 1e-3)
        wrote |= add_field(point, "velocity_north_ms", getattr(msg, "vx", None), 1e-2)
        wrote |= add_field(point, "velocity_east_ms", getattr(msg, "vy", None), 1e-2)
        wrote |= add_field(point, "velocity_down_ms", getattr(msg, "vz", None), 1e-2)

        heading = getattr(msg, "hdg", None)
        if heading not in (None, 65535):
            wrote |= add_field(point, "heading_deg", heading, 1e-2)

        vx = getattr(msg, "vx", None)
        vy = getattr(msg, "vy", None)
        if valid_number(vx) and valid_number(vy):
            wrote |= add_field(
                point,
                "groundspeed_from_velocity_ms",
                math.hypot(float(vx), float(vy)) / 100.0,
            )

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

    elif msg_type == "BATTERY_STATUS":
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

    elif msg_type == "GPS_RAW_INT":
        fix_type = getattr(msg, "fix_type", None)
        if valid_number(fix_type):
            point.field("gps_fix_type", int(fix_type))
            wrote = True

        satellites = getattr(msg, "satellites_visible", None)
        if satellites not in (None, 255) and valid_number(satellites):
            point.field("satellites_visible", int(satellites))
            wrote = True

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

    return point if wrote else None


def sonar_point(
    row: pd.Series,
    replay_time: datetime,
    run_name: str,
) -> Point | None:
    point = (
        Point(SONAR_MEASUREMENT)
        .tag("run", run_name)
        .tag("source", "sonar_csv_replay")
        .time(replay_time, WritePrecision.NS)
    )

    if "source_file" in row and pd.notna(row["source_file"]):
        point.tag("source_file", str(row["source_file"]))

    wrote = False
    for source_column, field_name in SONAR_FIELD_MAP.items():
        if source_column not in row:
            continue
        value = row[source_column]
        if pd.isna(value):
            continue
        try:
            point.field(field_name, float(value))
            wrote = True
        except (TypeError, ValueError):
            pass

    return point if wrote else None


def read_tlog_events(path: Path) -> list[ReplayEvent]:
    connection = mavutil.mavlink_connection(str(path))
    events: list[ReplayEvent] = []

    while True:
        msg = connection.recv_match(blocking=False)
        if msg is None:
            break

        if msg.get_type() not in SUPPORTED_TYPES:
            continue

        timestamp = getattr(msg, "_timestamp", None)
        if not valid_number(timestamp):
            continue

        events.append(ReplayEvent(float(timestamp), "tlog", msg))

    return events


def read_sonar_events(path: Path) -> list[ReplayEvent]:
    df = pd.read_csv(path)
    df.columns = [str(column).strip() for column in df.columns]

    time_column = next(
        (name for name in ("datetime", "time_readable", "timestamp") if name in df.columns),
        None,
    )
    if time_column is None:
        raise ValueError(
            "Sonar CSV needs a datetime, time_readable, or timestamp column."
        )

    if time_column == "timestamp":
        parsed = pd.to_datetime(df[time_column], unit="s", utc=True, errors="coerce")
    else:
        parsed = pd.to_datetime(df[time_column], utc=True, errors="coerce")

    events: list[ReplayEvent] = []
    for index, timestamp in parsed.items():
        if pd.isna(timestamp):
            continue
        events.append(
            ReplayEvent(
                original_time=timestamp.timestamp(),
                source="sonar",
                payload=df.loc[index],
            )
        )
    return events


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay historical BlueBoat telemetry as live InfluxDB data."
    )
    parser.add_argument("tlog", type=Path, help="Path to the mission .tlog file")
    parser.add_argument("--sonar-csv", type=Path, help="Optional merged sonar CSV")
    parser.add_argument(
        "--speed",
        type=float,
        default=20.0,
        help="Replay multiplier. Example: 20 replays 20x faster.",
    )
    parser.add_argument(
        "--run",
        default="live_replay",
        help="Replay run tag used by Grafana",
    )
    parser.add_argument(
        "--write-interval",
        type=float,
        default=0.5,
        help="Seconds between InfluxDB writes",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.speed <= 0:
        raise ValueError("--speed must be greater than zero")
    if not args.tlog.exists():
        raise FileNotFoundError(f"TLOG not found: {args.tlog}")
    if args.sonar_csv and not args.sonar_csv.exists():
        raise FileNotFoundError(f"Sonar CSV not found: {args.sonar_csv}")

    influx_url = os.environ.get("INFLUX_URL", "http://localhost:8086")
    influx_org = os.environ.get("INFLUX_ORG", "caltech_lab")
    influx_bucket = os.environ.get("INFLUX_BUCKET", "qgc_data")
    influx_token = os.environ.get("INFLUX_TOKEN")

    if not influx_token:
        raise RuntimeError(
            "INFLUX_TOKEN is not set. Run: set -a && source .env && set +a"
        )

    print("Reading TLOG...")
    events = read_tlog_events(args.tlog)
    print(f"  Telemetry events: {len(events):,}")

    if args.sonar_csv:
        print("Reading sonar CSV...")
        sonar_events = read_sonar_events(args.sonar_csv)
        events.extend(sonar_events)
        print(f"  Sonar events: {len(sonar_events):,}")

    if not events:
        raise RuntimeError("No replayable events found.")

    events.sort(key=lambda event: event.original_time)

    original_start = events[0].original_time
    original_end = events[-1].original_time
    original_duration = original_end - original_start
    replay_duration = original_duration / args.speed

    print()
    print("Replay configuration")
    print(f"  Run tag:         {args.run}")
    print(f"  Original length: {original_duration / 60:.1f} min")
    print(f"  Replay speed:    {args.speed:g}x")
    print(f"  Replay length:   {replay_duration / 60:.1f} min")
    print("  Starting in 3 seconds...")
    time.sleep(3)

    replay_start_utc = datetime.now(timezone.utc)
    wall_start = time.monotonic()
    last_write = wall_start
    pending: list[Point] = []
    written = 0

    with InfluxDBClient(
        url=influx_url,
        token=influx_token,
        org=influx_org,
        timeout=60_000,
    ) as client:
        write_api = client.write_api(write_options=SYNCHRONOUS)

        for index, event in enumerate(events, start=1):
            relative_seconds = event.original_time - original_start
            due_wall_seconds = relative_seconds / args.speed

            while time.monotonic() - wall_start < due_wall_seconds:
                time.sleep(0.02)

            replay_time = replay_start_utc + timedelta(seconds=due_wall_seconds)

            if event.source == "tlog":
                point = telemetry_point(event.payload, replay_time, args.run)
            else:
                point = sonar_point(event.payload, replay_time, args.run)

            if point is not None:
                pending.append(point)

            now = time.monotonic()
            if (
                pending
                and (
                    now - last_write >= args.write_interval
                    or index == len(events)
                    or len(pending) >= 2000
                )
            ):
                write_api.write(
                    bucket=influx_bucket,
                    org=influx_org,
                    record=pending,
                )
                written += len(pending)
                pending.clear()
                last_write = now

                progress = 100 * index / len(events)
                print(
                    f"\rReplay {progress:6.2f}% | points written: {written:,}",
                    end="",
                    flush=True,
                )

    print()
    print("Replay complete.")
    print(f"Run tag: {args.run}")
    print(f"Points written: {written:,}")


if __name__ == "__main__":
    main()
