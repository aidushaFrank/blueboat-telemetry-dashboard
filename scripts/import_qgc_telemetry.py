from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pandas as pd
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def find_input_file() -> Path:
    candidates = [p for p in DATA_DIR.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS]
    if not candidates:
        raise FileNotFoundError(
            "No input file found in data/. "
        )
    candidates.sort()
    return candidates[0]


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


def choose_first_present(df: pd.DataFrame, options: list[str]) -> Optional[str]:
    for col in options:
        if col in df.columns:
            return col
    return None


def parse_time_column(df: pd.DataFrame) -> pd.Series:
    if "time_readable" in df.columns:
        return pd.to_datetime(df["time_readable"], errors="coerce")
    if "timestamp" in df.columns:
        # assumes unix seconds
        return pd.to_datetime(df["timestamp"], unit="s", errors="coerce", utc=True).dt.tz_convert(None)
    raise ValueError("Need either 'time_readable' or 'timestamp' column")


def main() -> None:
    influx_url = os.environ.get("INFLUX_URL", "http://localhost:8086")
    influx_org = os.environ["INFLUX_ORG"]
    influx_bucket = os.environ["INFLUX_BUCKET"]
    influx_token = os.environ["INFLUX_TOKEN"]

    input_file = find_input_file()
    run_name = input_file.stem

    df = read_table(input_file)
    df.columns = [str(c).strip() for c in df.columns]

    lat_col = choose_first_present(df, ["lat_clean", "lat"])
    lon_col = choose_first_present(df, ["lon_clean", "lon"])
    alt_col = choose_first_present(df, ["alt_m", "alt"])
    rel_alt_col = choose_first_present(df, ["relative_alt_m", "relative_alt"])
    heading_col = choose_first_present(df, ["heading_deg", "hdg", "heading"])
    speed_col = choose_first_present(df, ["speed_xy", "speed_xy_raw"])

    if lat_col is None or lon_col is None:
        raise ValueError("Need latitude/longitude columns")

    df["_time"] = parse_time_column(df)
    df = df.dropna(subset=["_time", lat_col, lon_col]).copy()

    numeric_candidates = [lat_col, lon_col, alt_col, rel_alt_col, heading_col, speed_col]
    for col in numeric_candidates:
        if col and col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    with InfluxDBClient(url=influx_url, token=influx_token, org=influx_org) as client:
        write_api = client.write_api(write_options=SYNCHRONOUS)
        points: list[Point] = []

        for _, row in df.iterrows():
            point = (
                Point("qgc_telemetry")
                .tag("source", "qgroundcontrol")
                .tag("run", run_name)
                .time(row["_time"], WritePrecision.NS)
                .field("lat", float(row[lat_col]))
                .field("lon", float(row[lon_col]))
            )

            if alt_col and pd.notna(row.get(alt_col)):
                point.field("alt_m", float(row[alt_col]))
            if rel_alt_col and pd.notna(row.get(rel_alt_col)):
                point.field("relative_alt_m", float(row[rel_alt_col]))
            if heading_col and pd.notna(row.get(heading_col)):
                point.field("heading_deg", float(row[heading_col]))
            if speed_col and pd.notna(row.get(speed_col)):
                point.field("speed_xy", float(row[speed_col]))

            gps_point = (
                Point("gps_track")
                .tag("track", run_name)
                .tag("source", "qgroundcontrol")
                .time(row["_time"], WritePrecision.NS)
                .field("lat", float(row[lat_col]))
                .field("lon", float(row[lon_col]))
            )
            if alt_col and pd.notna(row.get(alt_col)):
                gps_point.field("alt_m", float(row[alt_col]))

            points.extend([point, gps_point])

        write_api.write(bucket=influx_bucket, record=points)

    print(f"Imported {len(df)} rows from {input_file.name} into bucket '{influx_bucket}'.")
    print(f"Run tag: {run_name}")


if __name__ == "__main__":
    main()
