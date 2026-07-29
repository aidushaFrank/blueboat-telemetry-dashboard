from __future__ import annotations

import os
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pandas as pd
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS


DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "merged_sonar_gps.csv"

MEASUREMENT = "sonar_path_depth"
DEFAULT_RUN_TAG = "live_replay_sonar_2026_06_22"


def prepare_ping_summary(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing CSV file: {csv_path}")

    df = pd.read_csv(csv_path)
    df.columns = [str(c).strip() for c in df.columns]

    required_columns = [
        "sonar_timestamp_utc",
        "latitude",
        "longitude",
        "altitude (m)",
        "ping number",
    ]

    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["_original_time"] = pd.to_datetime(
        df["sonar_timestamp_utc"],
        utc=True,
        errors="coerce",
    )

    numeric_columns = [
        "latitude",
        "longitude",
        "altitude (m)",
        "northing (local m)",
        "easting (local m)",
        "ping number",
        "elapsed (s)",
        "gps_speed_mps",
        "gps_heading_deg",
        "gps_gap_seconds",
    ]

    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "gps_interpolation_valid" in df.columns:
        df["gps_interpolation_valid"] = (
            df["gps_interpolation_valid"]
            .astype(str)
            .str.lower()
            .isin(["true", "1", "yes"])
        )
        df = df[df["gps_interpolation_valid"] == True].copy()

    df = df.dropna(
        subset=[
            "_original_time",
            "latitude",
            "longitude",
            "altitude (m)",
            "ping number",
        ]
    ).copy()

    # SonarView altitude is negative-down in this file.
    # Convert to positive depth for dashboard display.
    df["depth_m"] = -df["altitude (m)"]

    # One row per ping is better for Grafana path/map panels.
    ping_df = (
        df.groupby("ping number")
        .agg(
            original_time=("_original_time", "first"),
            latitude=("latitude", "median"),
            longitude=("longitude", "median"),
            depth_median_m=("depth_m", "median"),
            depth_min_m=("depth_m", "min"),
            depth_max_m=("depth_m", "max"),
            beam_returns=("depth_m", "count"),
            elapsed_s=("elapsed (s)", "median"),
            gps_speed_mps=("gps_speed_mps", "median"),
            gps_heading_deg=("gps_heading_deg", "median"),
            gps_gap_seconds=("gps_gap_seconds", "median"),
            local_northing_m=("northing (local m)", "median"),
            local_easting_m=("easting (local m)", "median"),
        )
        .reset_index()
        .rename(columns={"ping number": "ping_number"})
    )

    ping_df = ping_df.sort_values("original_time").reset_index(drop=True)

    return ping_df


def make_point(row: pd.Series, replay_time: datetime, run_tag: str) -> Point:
    point = (
        Point(MEASUREMENT)
        .tag("run", run_tag)
        .tag("source", "merged_sonar_gps_live_replay")
        .time(replay_time, WritePrecision.NS)
    )

    fields = [
        "latitude",
        "longitude",
        "depth_median_m",
        "depth_min_m",
        "depth_max_m",
        "beam_returns",
        "elapsed_s",
        "gps_speed_mps",
        "gps_heading_deg",
        "gps_gap_seconds",
        "local_northing_m",
        "local_easting_m",
    ]

    for field in fields:
        value = row.get(field)
        if pd.notna(value):
            point.field(field, float(value))

    return point


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay merged sonar+GPS CSV so Grafana looks live."
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=DATA_FILE,
        help="Path to merged_sonar_gps.csv",
    )
    parser.add_argument(
        "--run",
        default=DEFAULT_RUN_TAG,
        help="Run tag used in Grafana",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=10.0,
        help="Replay speed multiplier. Example: 10 means 10x faster.",
    )
    parser.add_argument(
        "--write-interval",
        type=float,
        default=0.5,
        help="How often to write batches to InfluxDB, in seconds.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.speed <= 0:
        raise ValueError("--speed must be greater than 0")

    influx_url = os.environ.get("INFLUX_URL", "http://localhost:8086")
    influx_org = os.environ.get("INFLUX_ORG", "caltech_lab")
    influx_bucket = os.environ.get("INFLUX_BUCKET", "qgc_data")
    influx_token = os.environ.get("INFLUX_TOKEN")

    if not influx_token:
        raise RuntimeError("INFLUX_TOKEN is not set. Check your .env file.")

    df = prepare_ping_summary(args.csv)

    original_start = df["original_time"].iloc[0]
    original_end = df["original_time"].iloc[-1]
    original_duration_s = (original_end - original_start).total_seconds()
    replay_duration_s = original_duration_s / args.speed

    print()
    print("Live replay configuration")
    print(f"  CSV:              {args.csv}")
    print(f"  Measurement:      {MEASUREMENT}")
    print(f"  Run tag:          {args.run}")
    print(f"  Points to replay: {len(df):,}")
    print(f"  Original start:   {original_start}")
    print(f"  Original end:     {original_end}")
    print(f"  Original length:  {original_duration_s / 60:.2f} min")
    print(f"  Replay speed:     {args.speed:g}x")
    print(f"  Replay length:    {replay_duration_s / 60:.2f} min")
    print()
    print("Starting in 3 seconds...")
    time.sleep(3)

    replay_start_utc = datetime.now(timezone.utc)
    wall_start = time.monotonic()
    last_write = wall_start
    pending = []
    written = 0

    with InfluxDBClient(
        url=influx_url,
        token=influx_token,
        org=influx_org,
        timeout=60_000,
    ) as client:
        write_api = client.write_api(write_options=SYNCHRONOUS)

        for index, row in df.iterrows():
            original_time = row["original_time"]
            relative_seconds = (original_time - original_start).total_seconds()
            due_wall_seconds = relative_seconds / args.speed

            while time.monotonic() - wall_start < due_wall_seconds:
                time.sleep(0.02)

            replay_time = replay_start_utc + timedelta(seconds=due_wall_seconds)

            point = make_point(row, replay_time, args.run)
            pending.append(point)

            now = time.monotonic()
            is_last = index == len(df) - 1

            if pending and (
                now - last_write >= args.write_interval
                or len(pending) >= 500
                or is_last
            ):
                write_api.write(
                    bucket=influx_bucket,
                    org=influx_org,
                    record=pending,
                )
                written += len(pending)
                pending.clear()
                last_write = now

                progress = 100 * (index + 1) / len(df)
                print(
                    f"\rReplay {progress:6.2f}% | points written: {written:,}",
                    end="",
                    flush=True,
                )

    print()
    print("Replay complete!")
    print(f"Run tag: {args.run}")
    print(f"Points written: {written:,}")


if __name__ == "__main__":
    main()