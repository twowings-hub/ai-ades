"""
AI-ADES Plasma 센서 ZIP 테스트 샘플 생성 (Phase 6)

250kHz CSV 포맷(Index;Time;Area;Plasma;P-Raw;Temp;T-Raw;Refl;R-Raw)을 흉내낸
합성 시계열 데이터를 exp_no="1"~"5" 5건에 대해 생성하여 ZIP으로 묶는다.
(experiments 테이블에 exp_no="1"~"5"가 존재해야 plasma_loader 적재 테스트 가능)

LSTM-Autoencoder 학습/예측 파이프라인 동작 확인용으로,
채널값은 정현파 + 노이즈로 생성해 윈도우 간 패턴 차이를 만든다.
"""
import math
import random
import zipfile
from io import StringIO

random.seed(42)

CHANNELS = ["Area", "Plasma", "P-Raw", "Temp", "T-Raw", "Refl", "R-Raw"]
SAMPLE_RATE_HZ = 250_000
N_SAMPLES = 500  # 테스트용 (실제로는 250kHz x 가공시간)
EXP_NOS = ["1", "2", "3", "4", "5"]


def make_csv(exp_no: str) -> str:
    buf = StringIO()
    buf.write(";".join(["Index", "Time"] + CHANNELS) + "\n")
    for i in range(N_SAMPLES):
        time_s = i / SAMPLE_RATE_HZ
        values = [
            round(50 + 30 * math.sin(i / 20 + ch_idx) + random.uniform(-2, 2), 4)
            for ch_idx in range(len(CHANNELS))
        ]
        buf.write(";".join([str(i), f"{time_s:.8f}"] + [str(v) for v in values]) + "\n")
    return buf.getvalue()


path = r"D:\claude\ai-ades\data\test\AI-ADES_test_plasma_sample.zip"
with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
    for exp_no in EXP_NOS:
        zf.writestr(f"{exp_no}.csv", make_csv(exp_no))

print(f"saved: {path}")
