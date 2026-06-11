"""
AI-ADES 업로드 테스트용 샘플 Excel 10개 생성 (각 10행)
POC 업로드 형식(Data 시트 + Sheet1 시트, header=1)에 맞춰 생성한다.
"""
import random

import openpyxl

random.seed(42)

M1_M2_OPTIONS = [
    ("Glass", 4, "Film", 10),
    ("Glass", 10, "Film", 25),
    ("Glass", 20, "Film", 50),
    ("Glass", 10, "Film", 50),
    ("Glass", 20, "Film", 25),
]
SPEED_OPTIONS = [200, 500, 1000]
DEFOCUS_OPTIONS = [0, 1, 2, 3, 4]
FREQUENCY_OPTIONS = [100, 200]


def make_row(no):
    m1, m1_len, m2, m2_len = random.choice(M1_M2_OPTIONS)
    thickness = round(random.uniform(98.0, 177.5), 1)
    speed = random.choice(SPEED_OPTIONS)
    defocus = random.choice(DEFOCUS_OPTIONS)
    frequency = random.choice(FREQUENCY_OPTIONS)
    power = round(random.uniform(2.8, 59.8), 2)
    kerf = round(random.uniform(150.0, 200.0), 1)

    # 최종 판정을 먼저 정한 뒤 그에 맞는 Depth 값을 생성한다 (judge_quality 기준)
    verdict = random.choices(["OK", "미가공", "과가공", "NG"], weights=[5, 2, 1, 1])[0]
    if verdict == "OK":
        depth = round(random.uniform(0.1, 25.0), 1)
    elif verdict == "미가공":
        depth = round(random.uniform(25.1, 60.0), 1)
    elif verdict == "과가공":
        depth = 0.0
    else:  # NG
        depth = round(random.uniform(0.1, 25.0), 1)

    sensor_missing = random.random() < 0.1  # 10% 확률로 센서 데이터 없음
    data_flag = "X" if sensor_missing else None

    data_row = (no, m1, m1_len, m2, m2_len, thickness, speed, defocus)
    sheet1_row = (frequency, power, data_flag, kerf, depth, verdict)
    return data_row, sheet1_row


def build_workbook(start_no):
    wb = openpyxl.Workbook()

    ws_data = wb.active
    ws_data.title = "Data"
    ws_data.append((None, "Sample", None, None, None, None, "Process", None))
    ws_data.append(["No.", "M1", "M1 length", "M2", "M2 length", "Thickness", "Speed", "Defocus"])

    ws_sheet1 = wb.create_sheet("Sheet1")
    ws_sheet1.append(("LASER", None, "sensor", "Result", None, None))
    ws_sheet1.append(["Frequency", "Power", "Data 유무", "Kerf", "Depth", "최종"])

    for i in range(10):
        data_row, sheet1_row = make_row(start_no + i)
        ws_data.append(data_row)
        ws_sheet1.append(sheet1_row)

    return wb


for file_idx in range(10):
    start_no = 2001 + file_idx * 10
    wb = build_workbook(start_no)
    path = rf"D:\claude\ai-ades\data\test\AI-ADES_test_upload_sample_{file_idx + 1:02d}.xlsx"
    wb.save(path)
    print(f"saved: {path} (No.{start_no}~{start_no + 9})")
