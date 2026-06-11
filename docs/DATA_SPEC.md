# AI-ADES 데이터 구조 상세

> CLAUDE.md 3장의 상세 버전. Excel POC 데이터 구조, 소재 종류 관리, 학습 데이터 범위.

---

## Excel POC 데이터 구조

```
파일: AI-ADES_POC_data_condition_results.xlsx
총 데이터: 328건 (No.1~355 중 결측 34건 제외)

Data 시트 (Sample + Process):
  No. / M1(Glass) / M1 length(4·10·20mm) / M2(Film) /
  M2 length(10·25·50mm) / Thickness(μm) / Speed(200·500·1000) / Defocus(0~4)

Sheet1 (Laser + Sensor + Result):
  Frequency(100·200kHz) / Power(2.8~59.8W) / Data유무(X=센서없음) /
  Kerf(μm) / Depth(μm) / 최종(미가공·OK·과가공·NG)

⚠ 두 시트는 행 순서 기준 1:1 조인 (No.1행 = Sheet1 1행, header=1)
```

- `excel_parser.parse_excel()`이 두 시트를 조인하여 `experiments` 테이블 컬럼으로 매핑
- `exp_no`는 `No.` 컬럼 (UNIQUE, 비정형 값 '300-2' 등 문자열 보존)
- `sensor_data_ok = (Data 유무 != "X")`
- `is_outlier = (Thickness > THICKNESS_OUTLIER_THRESHOLD_UM)` → `THICKNESS_OUTLIER_THRESHOLD_UM = 140.0`
- 업로드 시 `ON CONFLICT (exp_no) DO NOTHING`으로 중복 적재 방지 → 신규 파일은 기존 No.와 겹치지 않는 번호 사용

업로드 테스트용 샘플: `data/test/AI-ADES_test_upload_sample_01~10.xlsx` (각 10건, No.2001~2100, 생성 스크립트 `data/test/generate_test_files.py`)

---

## 판정 기준 (절대 변경 금지)

```python
# .env의 값을 사용할 것 (하드코딩 금지)
DEPTH_OK_MIN = 0.0    # μm 초과
DEPTH_OK_MAX = 25.0   # μm 이하
# 미가공: depth > 25μm
# OK    : 0 < depth ≤ 25μm  ← AI의 목표
# 과가공: depth = 0μm
# NG    : Defect 감지

QUALITY_SCORE = {"OK": 1, "미가공": 0, "과가공": -1, "NG": -2}
```

Admin Console에서 `PATCH /admin/settings/quality-criteria`로 `DEPTH_OK_MIN`/`DEPTH_OK_MAX`를 즉시 변경 가능 (audit_logs 기록).

---

## Bayesian Optimization 탐색 공간

```python
SEARCH_SPACE = {
    "speed":     {"type": "discrete", "values": [200, 500, 1000]},
    "defocus":   {"type": "discrete", "values": [0, 1, 2, 3, 4]},
    "frequency": {"type": "discrete", "values": [100, 200]},
    "power":     {"type": "continuous", "range": [2.8, 59.8]},
}
# 탐색 공간 외 값은 절대 제안하지 않음
```

Admin Console `PATCH /admin/settings/search-space`로 변경 시 Bayesian Opt 재초기화.

---

## 소재 종류 관리 (material_types)

- `material_types` 테이블: `category`('m1'=Glass계열 / 'm2'=Film계열'), `name`, `description`, `is_active`
- 기본 시드: `('m1','Glass')`, `('m2','Film')`
- Admin Console "소재 종류 관리" 섹션에서 CRUD (추가/수정/활성·비활성/삭제)
  - 삭제는 `material_types`에서만 제거되며, 기존 `experiments`/`recipes` 데이터의 소재명에는 영향 없음
- 실험 조건 입력 화면(`/material-types`, GET)에서 활성 항목만 노출되어 M1/M2 소재 종류 선택에 사용
- `recipes` 테이블/레시피 매칭(`recipe_db.find_recipe`)은 `m1_glass`/`m2_film` + 길이 + 두께(±`THICKNESS_TOLERANCE_UM=5.0`)로 매칭

---

## M1/M2 길이·두께 입력 및 외삽(extrapolation) 경고

- M1 length / M2 length / Thickness는 자유 숫자 입력 (프리셋 버튼은 빠른 선택용 참고치)
  - M1 프리셋: 4 / 10 / 20 mm, M2 프리셋: 10 / 25 / 50 mm
- `GET /data/distribution` (data-prep-agent)이 `data_ranges` 필드로 학습 데이터의 min/max를 제공
  - 현재 학습 데이터 범위: `m1_length_mm ∈ [4, 20]`, `m2_length_mm ∈ [10, 50]`, `thickness_um ∈ [98, 177.5]`
- 입력값이 이 범위를 벗어나면 ExperimentPage에 "⚠ 학습 데이터 범위를 벗어났습니다. 예측 신뢰도가 낮을 수 있습니다 (Auto DOE 탐색 횟수 증가 권장)" 경고 표시
- 모델 재학습으로 학습 데이터가 늘어나면 `data_ranges`도 자동으로 갱신됨 (별도 하드코딩 없음)
