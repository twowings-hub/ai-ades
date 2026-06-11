"""
AI-ADES Plasma 센서 ZIP 파서 (Phase 6)

CO2 레이저 가공 중 Plasma 센서로 수집한 250kHz 시계열 CSV(ZIP 묶음)를 파싱하여
plasma_timeseries 테이블 적재용 long-format DataFrame을 생성한다.

CSV 포맷 (세미콜론 구분):
    Index;Time;Area;Plasma;P-Raw;Temp;T-Raw;Refl;R-Raw
    - Index: 샘플 순번
    - Time : 가공 시작 후 경과 시간 (초)
    - 나머지: Plasma 센서 채널 값

ZIP 내부 CSV 파일명(확장자 제외)을 experiments.exp_no로 매핑한다.
(예: "1.csv", "300-2.csv")
"""
import os
import zipfile

import pandas as pd

# CSV의 센서 채널 컬럼 (plasma_timeseries.channel 값으로 그대로 사용)
PLASMA_CHANNELS = ["Area", "Plasma", "P-Raw", "Temp", "T-Raw", "Refl", "R-Raw"]

# CSV 필수 컬럼 (Index는 사용하지 않으므로 검증에서 제외)
REQUIRED_COLUMNS = ["Time"] + PLASMA_CHANNELS


def parse_plasma_zip(file_path: str) -> pd.DataFrame:
    """
    Plasma 센서 ZIP 파일을 파싱한다.

    Args:
        file_path: ZIP 파일 경로 (내부에 exp_no.csv 형태의 CSV 1개 이상 포함)

    Returns:
        long-format DataFrame (exp_no, elapsed_ms, channel, value 컬럼)
    """
    frames = []

    with zipfile.ZipFile(file_path) as zf:
        csv_names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError("ZIP 내부에 CSV 파일이 없습니다")

        for name in csv_names:
            exp_no = os.path.splitext(os.path.basename(name))[0]
            with zf.open(name) as f:
                raw_df = pd.read_csv(f, sep=";")

            missing = [col for col in REQUIRED_COLUMNS if col not in raw_df.columns]
            if missing:
                raise ValueError(f"{name}: 필수 컬럼 누락 {missing}")

            # Time(초) -> elapsed_ms(밀리초), wide -> long 변환
            raw_df["elapsed_ms"] = raw_df["Time"].astype(float) * 1000.0
            long_df = raw_df.melt(
                id_vars=["elapsed_ms"],
                value_vars=PLASMA_CHANNELS,
                var_name="channel",
                value_name="value",
            )
            long_df["value"] = long_df["value"].astype(float)
            long_df["exp_no"] = exp_no
            frames.append(long_df)

    result = pd.concat(frames, ignore_index=True)
    _print_summary(result)

    return result


def _print_summary(df: pd.DataFrame) -> None:
    """파싱 결과(실험 건수, 총 샘플 수)를 콘솔에 출력한다."""
    n_exp = df["exp_no"].nunique()
    n_samples = len(df) // len(PLASMA_CHANNELS)
    print(
        f"Plasma 파싱 완료: 실험 {n_exp}건, 채널 {len(PLASMA_CHANNELS)}개, "
        f"샘플 {n_samples}개 (총 {len(df)}행)"
    )


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "data/test/AI-ADES_test_plasma_sample.zip"
    parse_plasma_zip(path)
