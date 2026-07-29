from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS


# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "merged_sonar_gps.csv"

MEASUREMENT = "sonar_path_depth"
RUN_TAG = "sonar_2026_06_22"


def main() -> None:
    influx_url = os.environ.get("INFLUX_URL", "http://localhost:8086")
    influx_org = os.environ.get("INFLUX_ORG", "caltech_lab")
    influx_bucket = os.environ.get("INFLUX_BUCKET", "qgc_data")
    influx_token = os.environ.get("INFLUX_TOKEN")

    if not influx_token:
        raise RuntimeError("INFLUX_TOKEN is not set. Check your .env file.")

    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Missing CSV file: {DATA_FILE}")

    print(f"Reading: {DATA_FILE}")

    df = pd.read_csv(DATA_FILE)
    df.columns = [str(c).strip() for c in df.columns]

    # ---------------------------------------------------------
    # Basic cleaning
    # ---------------------------------------------------------

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

    df["_time"] = pd.to_datetime(
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
        "gps_altitude_m",
        "gps_relative_altitude_m",
        "gps_velocity_north_mps",
        "gps_velocity_east_mps",
        "gps_velocity_down_mps",
        "gps_speed_mps",
        "gps_heading_deg",
        "gps_gap_seconds",
    ]

    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Keep only rows that actually have GPS.
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
            "_time",
            "latitude",
            "longitude",
            "altitude (m)",
            "ping number",
        ]
    ).copy()

    # Convert SonarView negative altitude into positive demo depth.
    # Example: altitude = -5 m -> depth_m = 5 m
    df["depth_m"] = -df["altitude (m)"]

    # Remove obviously weird values for demo panels.
    # Keep this generous, but avoid insane outliers.
    df["depth_quality"] = "ok"
    df.loc[df["depth_m"] < 0, "depth_quality"] = "bad_negative_depth"
    df.loc[df["depth_m"] > 20, "depth_quality"] = "review_deep_return"

    # ---------------------------------------------------------
    # Collapse multibeam rows into one row per ping
    # This is best for Grafana path map.
    # ---------------------------------------------------------

    group_cols = ["ping number"]

    ping_df = (
        df.groupby(group_cols)
        .agg(
            _time=("_time", "first"),
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

    ping_df = ping_df.sort_values("_time").copy()

    print(f"Rows in original valid sonar data: {len(df):,}")
    print(f"Rows after one-row-per-ping summary: {len(ping_df):,}")
    print(f"Time start: {ping_df['_time'].min()}")
    print(f"Time end:   {ping_df['_time'].max()}")

    # ---------------------------------------------------------
    # Write to InfluxDB
    # ---------------------------------------------------------

    points: list[Point] = []

    for _, row in ping_df.iterrows():
        point = (
            Point(MEASUREMENT)
            .tag("run", RUN_TAG)
            .tag("source", "merged_sonar_gps_csv")
            .time(row["_time"].to_pydatetime(), WritePrecision.NS)
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

        wrote_field = False

        for field in fields:
            value = row.get(field)
            if pd.notna(value):
                point.field(field, float(value))
                wrote_field = True

        if wrote_field:
            points.append(point)

    with InfluxDBClient(
        url=influx_url,
        token=influx_token,
        org=influx_org,
        timeout=60_000,
    ) as client:
        write_api = client.write_api(write_options=SYNCHRONOUS)

        write_api.write(
            bucket=influx_bucket,
            org=influx_org,
            record=points,
        )

    print()
    print("Import complete!")
    print(f"Bucket:      {influx_bucket}")
    print(f"Measurement: {MEASUREMENT}")
    print(f"Run tag:     {RUN_TAG}")
    print(f"Points:      {len(points):,}")


if __name__ == "__main__":
    main()