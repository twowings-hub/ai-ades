"""
AI-ADES Excel 파서

POC 데이터 Excel(Data 시트 + Sheet1)을 행 순서 기준 1:1로 조인하여
experiments 테이블 적재용 DataFrame을 생성한다.
"""
import pandas as pd

# 판정 -> quality_score 매핑 (CLAUDE.md 섹션 4 기준, 절대 변경 금지)
QUALITY_SCORE_MAP = {"OK": 1, "미가공": 0, "과가공": -1, "NG": -2}

# 이상값 플래그 기준: Thickness > 140um
THICKNESS_OUTLIER_THRESHOLD_UM = 140.0


def parse_excel(file_path: str) -> pd.DataFrame:
    """
    POC Excel 파일을 파싱하여 experiments 테이블 적재용 DataFrame을 반환한다.

    Args:
        file_path: Excel 파일 경로 (Data, Sheet1 시트 포함)

    Returns:
        파싱된 DataFrame (exp_no, m1_glass, m1_length_mm, m2_film, m2_length_mm,
        thickness_um, speed, defocus, frequency, power, sensor_data_ok,
        kerf_um, depth_um, quality, quality_score, is_outlier 컬럼 포함)
    """
    xls = pd.ExcelFile(file_path)

    # 1행: 그룹 헤더(Sample/Process/LASER 등), 2행: 실제 컬럼명 -> header=1
    data_df = pd.read_excel(xls, sheet_name="Data", header=1)
    sheet1_df = pd.read_excel(xls, sheet_name="Sheet1", header=1)

    # No.가 없는 행(결측)은 건너뜀 -> Data/Sheet1 동일 행수 유지
    data_df = data_df.dropna(subset=["No."]).reset_index(drop=True)
    sheet1_df = sheet1_df.iloc[: len(data_df)].reset_index(drop=True)

    df = pd.DataFrame(
        {
            # exp_no 비정형 처리: '300-2' 같은 케이스도 문자열 그대로 보존
            "exp_no": data_df["No."].astype(str),
            "m1_glass": data_df["M1"],
            "m1_length_mm": data_df["M1 length"],
            "m2_film": data_df["M2"],
            "m2_length_mm": data_df["M2 length"],
            "thickness_um": data_df["Thickness"],
            "speed": data_df["Speed"],
            "defocus": data_df["Defocus"],
            "frequency": sheet1_df["Frequency"],
            "power": sheet1_df["Power"],
            "kerf_um": sheet1_df["Kerf"],
            "depth_um": sheet1_df["Depth"],
            "quality": sheet1_df["최종"],
        }
    )

    # 센서 데이터 유무: 'Data 유무' 컬럼이 'X'면 센서 없음(False), 그 외(NaN 포함)는 True
    df["sensor_data_ok"] = sheet1_df["Data 유무"] != "X"

    # quality_score 파생 (OK=1, 미가공=0, 과가공=-1, NG=-2)
    df["quality_score"] = df["quality"].map(QUALITY_SCORE_MAP).astype("Int64")

    # 이상값 플래그: Thickness > 140um
    df["is_outlier"] = df["thickness_um"] > THICKNESS_OUTLIER_THRESHOLD_UM

    _print_summary(df)

    return df


def _print_summary(df: pd.DataFrame) -> None:
    """파싱 결과 건수 및 품질 분포를 콘솔에 출력한다."""
    dist = df["quality"].value_counts().to_dict()
    no_sensor = int((~df["sensor_data_ok"]).sum())
    print(
        f"파싱 완료: {len(df)}건 | "
        f"OK:{dist.get('OK', 0)} 미가공:{dist.get('미가공', 0)} "
        f"과가공:{dist.get('과가공', 0)} NG:{dist.get('NG', 0)} "
        f"센서없음:{no_sensor}"
    )


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "data/raw/AI-ADES_POC_data_condition_results.xlsx"
    parse_excel(path)
