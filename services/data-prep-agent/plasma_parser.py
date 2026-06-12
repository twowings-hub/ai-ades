"""
AI-ADES Plasma 센서 ZIP 파서 (Phase 6)

CO2 레이저 가공 중 Plasma 센서로 수집한 250kHz 시계열 CSV(ZIP 묶음)를 파싱하여
plasma_timeseries / plasma_measurements 테이블 적재용 데이터를 생성한다.

CSV 포맷 (이중 구분자):
    - 메타데이터 줄 (콜론 ':' 구분, "Index;Time;..." 헤더 줄 이전에 위치):
        Configuration: ... / Duration: ... / Sample Rate: ... / ConfigID: ...
        Comment: ... / MeasurementID: ... / Result: ... / Date: ...
    - 시계열 줄 (세미콜론 ';' 구분, "Index;Time;..." 헤더 줄부터 시작):
        Index;Time;Area;Plasma;P-Raw;Temp;T-Raw;Refl;R-Raw
    - 250kHz, 0.1초 측정 -> 최대 25,000행

ZIP 내부 CSV 파일명(확장자 제외)을 experiments.exp_no로 매핑한다.
(예: "1.csv", "300-2.csv")
"""
import io
import os
import zipfile

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# CSV의 센서 채널 컬럼 (plasma_timeseries.channel 값으로 그대로 사용)
PLASMA_CHANNELS = ["Area", "Plasma", "P-Raw", "Temp", "T-Raw", "Refl", "R-Raw"]

# 시계열 영역 시작을 알리는 헤더 줄 (이 줄부터 세미콜론 구분 시계열)
TS_HEADER_PREFIX = "Index;Time"

# CSV 필수 컬럼 (Index는 사용하지 않으므로 검증에서 제외)
REQUIRED_COLUMNS = ["Time"] + PLASMA_CHANNELS

# 1차 구간 분리 기준 (Time, 초 단위) - M1: 0~M1_END_S, M2: M1_END_S~M2_END_S, 그 외: Blank
M1_END_S = float(os.getenv("PLASMA_M1_END_S", 0.02))
M2_END_S = float(os.getenv("PLASMA_M2_END_S", 0.07))

# 전체 측정 시간이 이 값에서 PLASMA_TIME_TOLERANCE_S 이상 벗어나면 time_shifted=True
EXPECTED_DURATION_S = float(os.getenv("PLASMA_EXPECTED_DURATION_S", 0.1))
TIME_TOLERANCE_S = float(os.getenv("PLASMA_TIME_TOLERANCE_S", 0.005))

# 2차 검증: 구간 평균 Plasma 신호가 이 값 미만이면 해당 구간 미측정으로 판단
DETECT_THRESHOLD = float(os.getenv("PLASMA_DETECT_THRESHOLD", 5.0))

# 다운샘플링 비율 (250kHz -> 250kHz / factor)
DOWNSAMPLE_FACTOR = int(os.getenv("PLASMA_DOWNSAMPLE_FACTOR", 100))


def parse_plasma_csv(path_or_buffer, exp_no: str | None = None) -> tuple[dict, pd.DataFrame]:
    """
    Plasma CSV(이중 구분자) 1개를 파싱한다.

    Args:
        path_or_buffer: CSV 파일 경로 또는 파일 객체(zipfile.open() 결과 등)
        exp_no: 실험 번호 (경로에서 추출 가능하면 생략 가능)

    Returns:
        (meta, ts)
        - meta: 콜론(:) 구분 메타데이터 줄에서 추출한 딕셔너리
                (Configuration/Duration/Sample Rate/ConfigID/Comment/MeasurementID/Result/Date + exp_no)
        - ts  : 세미콜론(;) 구분 시계열 DataFrame (Time + PLASMA_CHANNELS 컬럼, float)
    """
    if hasattr(path_or_buffer, "read"):
        raw = path_or_buffer.read()
        text = raw.decode("utf-8-sig", errors="replace") if isinstance(raw, bytes) else raw
    else:
        if exp_no is None:
            exp_no = os.path.splitext(os.path.basename(path_or_buffer))[0]
        with open(path_or_buffer, "r", encoding="utf-8-sig", errors="replace") as f:
            text = f.read()

    meta: dict = {"exp_no": exp_no}
    ts_lines: list[str] = []
    header_found = False

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        if not header_found:
            if stripped.startswith(TS_HEADER_PREFIX):
                header_found = True
                ts_lines.append(stripped)
            elif ":" in stripped:
                key, _, value = stripped.partition(":")
                meta[key.strip()] = value.strip()
            # 그 외 (메타/헤더 모두 아닌 줄)는 무시
        else:
            ts_lines.append(stripped)

    if not header_found:
        raise ValueError(f"{exp_no}: 'Index;Time;...' 헤더 줄을 찾을 수 없습니다")

    ts = pd.read_csv(io.StringIO("\n".join(ts_lines)), sep=";")

    missing = [col for col in REQUIRED_COLUMNS if col not in ts.columns]
    if missing:
        raise ValueError(f"{exp_no}: 시계열 필수 컬럼 누락 {missing}")

    for col in REQUIRED_COLUMNS:
        ts[col] = ts[col].astype(float)

    return meta, ts


def detect_region(df: pd.DataFrame) -> dict:
    """
    Time 기준으로 M1/M2/Blank 구간을 1차 분리하고, 구간별 Plasma 신호 평균으로
    실제 측정 여부를 2차 검증한다. df에 "region" 컬럼을 추가한다 (in-place).

    Returns:
        {
          "m1_measured": bool,  # M1 구간 Plasma 신호가 임계값 이상인지
          "m2_measured": bool,  # M2 구간 Plasma 신호가 임계값 이상인지
          "time_shifted": bool, # 전체 측정 시간이 기대값(0.1s)에서 벗어났는지
        }
    """
    df["region"] = np.select(
        [df["Time"] < M1_END_S, df["Time"] < M2_END_S],
        ["M1", "M2"],
        default="Blank",
    )

    def _mean_plasma(region: str) -> float:
        values = df.loc[df["region"] == region, "Plasma"]
        return float(values.mean()) if not values.empty else 0.0

    actual_duration = float(df["Time"].max())

    return {
        "m1_measured": _mean_plasma("M1") >= DETECT_THRESHOLD,
        "m2_measured": _mean_plasma("M2") >= DETECT_THRESHOLD,
        "time_shifted": abs(actual_duration - EXPECTED_DURATION_S) > TIME_TOLERANCE_S,
    }


def downsample(df: pd.DataFrame, factor: int = DOWNSAMPLE_FACTOR) -> pd.DataFrame:
    """
    행 단위 균등 샘플링으로 다운샘플링한다 (LSTM-Autoencoder 입력용).
    예: 250kHz, factor=100 -> 2.5kHz
    """
    if factor <= 1:
        return df.reset_index(drop=True)
    return df.iloc[::factor].reset_index(drop=True)


def parse_plasma_zip(file_path: str) -> list[dict]:
    """
    ZIP 내 모든 Plasma CSV를 파싱하여 구간 분리/검증/다운샘플링까지 수행한다.

    Returns:
        파일별 결과 리스트. 각 항목:
        {
          "exp_no": str,
          "meta": dict,            # parse_plasma_csv() 결과 meta
          "df": DataFrame,         # downsample() 결과 (Time, PLASMA_CHANNELS, region 포함)
          "flags": dict,           # detect_region() 결과
          "warnings": list[str],   # 예외 케이스 경고 메시지
        }
    """
    results = []

    with zipfile.ZipFile(file_path) as zf:
        csv_names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError("ZIP 내부에 CSV 파일이 없습니다")

        for name in csv_names:
            exp_no = os.path.splitext(os.path.basename(name))[0]
            with zf.open(name) as f:
                meta, df = parse_plasma_csv(f, exp_no=exp_no)

            warnings: list[str] = []
            if "MeasurementID" not in meta:
                warnings.append("MeasurementID 누락")
            if "Result" not in meta:
                warnings.append("Result 누락")

            flags = detect_region(df)
            if not flags["m1_measured"] and not flags["m2_measured"]:
                warnings.append("M1+M2 미측정")
            elif not flags["m1_measured"]:
                warnings.append("M1 미측정")
            if flags["time_shifted"]:
                warnings.append("시간 구간 변동(time_shifted)")

            results.append(
                {
                    "exp_no": exp_no,
                    "meta": meta,
                    "df": downsample(df),
                    "flags": flags,
                    "warnings": warnings,
                }
            )

    _print_summary(results)
    return results


def _print_summary(results: list[dict]) -> None:
    """파싱 결과(파일 수, 경고 건수)를 콘솔에 출력한다."""
    n_warn = sum(1 for r in results if r["warnings"])
    print(f"Plasma 파싱 완료: 파일 {len(results)}건, 경고 {n_warn}건")
    for r in results:
        if r["warnings"]:
            print(f"  - {r['exp_no']}: {', '.join(r['warnings'])}")


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "data/test/AI-ADES_test_plasma_sample.zip"
    parse_plasma_zip(path)
