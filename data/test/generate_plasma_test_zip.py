"""
AI-ADES Plasma 센서 ZIP 테스트 샘플 생성 (Phase 6)

이중 구분자 포맷(메타데이터: 콜론 구분, 시계열: 세미콜론 구분
"Index;Time;Area;Plasma;P-Raw;Temp;T-Raw;Refl;R-Raw")을 흉내낸
합성 시계열 데이터를 exp_no="1"~"5" 5건에 대해 생성하여 ZIP으로 묶는다.
(experiments 테이블에 exp_no="1"~"5"가 존재해야 plasma_loader 적재 테스트 가능)

250kHz, 0.1초 측정을 그대로 흉내내며(실험당 25,000행),
plasma_parser의 기본 구간 경계(M1: 0~0.02s, M2: 0.02~0.07s, Blank: 0.07s~)에 맞춰
M1/M2 구간별로 Plasma 신호 강도를 다르게 생성한다.

- exp_no="1": M1/M2 모두 정상 측정
- exp_no="2": M1 미측정 (Plasma 신호 낮음, Power 부족 케이스)
- exp_no="3": M1+M2 모두 미측정
- exp_no="4": 시간 구간 변동(time_shifted, 전체 측정시간이 0.1s보다 짧음)
- exp_no="5": MeasurementID/Result 메타 누락
"""
import math
import random
import zipfile
from io import StringIO

random.seed(42)

CHANNELS = ["Area", "Plasma", "P-Raw", "Temp", "T-Raw", "Refl", "R-Raw"]
SAMPLE_RATE_HZ = 250_000
DURATION_S = 0.1
N_SAMPLES = int(DURATION_S * SAMPLE_RATE_HZ)  # 25,000 샘플

# plasma_parser 기본 구간 경계(PLASMA_M1_END_S=0.02 / PLASMA_M2_END_S=0.07)와 동일
M1_END_S = 0.02
M2_END_S = 0.07

CASES = {
    "1": {"m1": True, "m2": True, "short_duration": False, "drop_meta": False},
    "2": {"m1": False, "m2": True, "short_duration": False, "drop_meta": False},
    "3": {"m1": False, "m2": False, "short_duration": False, "drop_meta": False},
    "4": {"m1": True, "m2": True, "short_duration": True, "drop_meta": False},
    "5": {"m1": True, "m2": True, "short_duration": False, "drop_meta": True},
}


def make_csv(exp_no: str) -> str:
    case = CASES[exp_no]
    buf = StringIO()

    # ---- 메타데이터 (콜론 구분) ----
    buf.write("Configuration:DefaultConfig\n")
    duration = DURATION_S * 0.5 if case["short_duration"] else DURATION_S
    buf.write(f"Duration:{duration}\n")
    buf.write(f"Sample Rate:{SAMPLE_RATE_HZ}\n")
    buf.write("ConfigID:1\n")
    buf.write(f"Comment:Test case {exp_no}\n")
    if not case["drop_meta"]:
        buf.write(f"MeasurementID:{1000 + int(exp_no)}\n")
        buf.write("Result:OK\n")
    buf.write("Date:2026-06-01 10:00:00\n")

    # ---- 시계열 (세미콜론 구분) ----
    buf.write(";".join(["Index", "Time"] + CHANNELS) + "\n")

    n_samples = N_SAMPLES // 2 if case["short_duration"] else N_SAMPLES
    for i in range(n_samples):
        time_s = i / SAMPLE_RATE_HZ

        if time_s < M1_END_S:
            region_active = case["m1"]
        elif time_s < M2_END_S:
            region_active = case["m2"]
        else:
            region_active = False

        plasma_base = 50 if region_active else 0
        values = [
            round(plasma_base + 30 * math.sin(i / 20 + ch_idx) * (1 if region_active else 0.05) + random.uniform(-2, 2), 4)
            for ch_idx in range(len(CHANNELS))
        ]
        buf.write(";".join([str(i), f"{time_s:.8f}"] + [str(v) for v in values]) + "\n")

    return buf.getvalue()


path = r"D:\claude\ai-ades\data\test\AI-ADES_test_plasma_sample.zip"
with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
    for exp_no in CASES:
        zf.writestr(f"{exp_no}.csv", make_csv(exp_no))

print(f"saved: {path}")
