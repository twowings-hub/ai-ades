"""
AI-ADES InfluxDB 적재

experiments DataFrame을 InfluxDB laser_process 버킷의
"experiment_result" measurement로 적재한다.
"""
import os

import pandas as pd
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

load_dotenv()

MEASUREMENT = "experiment_result"


def write_to_influx(df: pd.DataFrame) -> int:
    """
    experiments DataFrame을 InfluxDB에 적재한다.

    tags: exp_no, quality, m1_length, m2_length
    fields: speed, defocus, frequency, power, kerf, depth, quality_score

    Args:
        df: excel_parser.parse_excel()의 결과 DataFrame

    Returns:
        적재된 포인트 수
    """
    url = os.getenv("INFLUXDB_URL")
    token = os.getenv("INFLUXDB_TOKEN")
    org = os.getenv("INFLUXDB_ORG")
    bucket = os.getenv("INFLUXDB_BUCKET")

    points = []
    for _, row in df.iterrows():
        point = (
            Point(MEASUREMENT)
            .tag("exp_no", str(row["exp_no"]))
            .tag("quality", str(row["quality"]))
            .tag("m1_length", str(row["m1_length_mm"]))
            .tag("m2_length", str(row["m2_length_mm"]))
            .field("speed", float(row["speed"]))
            .field("defocus", float(row["defocus"]))
            .field("frequency", float(row["frequency"]))
            .field("power", float(row["power"]))
            .field("kerf", float(row["kerf_um"]))
            .field("depth", float(row["depth_um"]))
            .field("quality_score", int(row["quality_score"]))
            .time(pd.Timestamp.utcnow(), WritePrecision.NS)
        )
        points.append(point)

    with InfluxDBClient(url=url, token=token, org=org) as client:
        with client.write_api(write_options=SYNCHRONOUS) as write_api:
            write_api.write(bucket=bucket, org=org, record=points)

    return len(points)
