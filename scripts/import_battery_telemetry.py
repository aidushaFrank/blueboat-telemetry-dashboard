from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "battery_over_time.csv"


def main() -> None:
    influx_url = os.environ.get("INFLUX_URL", "http://localhost:8086")
    influx_org = os.environ["INFLUX_ORG"]
    influx_bucket = os.environ["INFLUX_BUCKET"]
    influx_token = os.environ["INFLUX_TOKEN"]

    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Missing file: {DATA_FILE}")

    df = pd.read_csv(DATA_FILE)
    df.columns = [str(c).strip() for c in df.columns]

    if "timestamp" not in df.columns:
        raise ValueError("battery_over_time.csv needs a 'timestamp' column")

    df["_time"] = pd.to_datetime(df["timestamp"], unit="s", errors="coerce", utc=True).dt.tz_convert(None)
    df = df.dropna(subset=["_time"]).copy()

    numeric_cols = [
        "battery_voltage_v",
        "current_a",
        "battery_remaining_pct",
        "current_consumed_mah",
        "energy_consumed_hj",
        "Vcc_v",
        "Vservo_v",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    with InfluxDBClient(url=influx_url, token=influx_token, org=influx_org) as client:
        write_api = client.write_api(write_options=SYNCHRONOUS)
        points = []

        for _, row in df.iterrows():
            point = (
                Point("qgc_battery")
                .tag("source", "qgroundcontrol")
                .tag("run", "gps_track_cleaned")
                .tag("msg_type", str(row["msg_type"]) if "msg_type" in row and pd.notna(row["msg_type"]) else "unknown")
                .time(row["_time"], WritePrecision.NS)
            )

            for field in numeric_cols:
                if field in df.columns and pd.notna(row.get(field)):
                    point.field(field, float(row[field]))

            points.append(point)

        write_api.write(bucket=influx_bucket, record=points)

    print(f"Imported {len(df)} battery rows into measurement 'qgc_battery'.")


if __name__ == "__main__":
    main()