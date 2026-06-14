# AI-ADES 프로토타입 개발 플랜 v3 (최종)
## AI Autonomous Data Evaluation System — 개발 착수 전 검토용

> **작성일**: 2025년 6월 (PPT + Excel 완전 분석 기반)
> **개발 장비**: MS Surface Laptop Studio 1 (RAM 32GB, NVIDIA GeForce RTX 3050 Ti Laptop GPU 탑재)
> **기존 환경**: rag-pm-matcher (Docker / Ollama / Qwen·Claude·ChatGPT / Qdrant / PostgreSQL)
> **개발 착수**: 본 플랜 검토 및 착수 지시 후 시작

---

## 1. 데이터 완전 분석 결과

### 1.1 공정 이해 — CO₂ 레이저 Film 절단 시스템

PPT 슬라이드 분석으로 파악된 실제 공정 구조입니다.

```
[설비 구조]
  CO₂ Laser + Plasma Sensor
  Stage가 M1·M2 방향으로 이동하면서 레이저 가공

[소재 (Sample)]
  M1: Glass (첫 번째로 레이저가 닿는 물질)
    - M1 length: 센싱 길이 (4 / 10 / 20 mm)
  M2: Film (PET 75μm + Adhesive 25μm 적층, 총 100μm 이상)
    - M2 length: 센싱 길이 (10 / 25 / 50 mm)
  Thickness: Film(M2) 실측 두께 [μm] — 목표값 100μm, 실제 약 ±20μm 변동

[입력 파라미터 (Input — AI가 최적화할 대상)]
  Process:
    Speed   [mm/s]: Stage 이동 속도 (200 / 500 / 1000)
    Defocus [mm] : 레이저 초점 Z축 이탈 거리 (0 / 1 / 2 / 3 / 4)
  Laser:
    Frequency [kHz]: 레이저 가공 주파수 (100 / 200)
    Power     [W]  : 레이저 출력 (2.8 ~ 59.8)

[센서 (Plasma Sensor)]
  - Photodiode 기반, Threshold 초과 시 0.1초간 기록
  - 250kHz 샘플링 → 시계열 CSV 파일 (별도 plasma sensor.zip)
  - 측정 채널: Plasma / Temp(Temperature) / Refl(Reflection)
  - M1 측정 → M2 측정 → Blank 순서로 기록
  - Power 약하면 센서 Data 없음 (7건, 'X' 표기)

[결과 (Result — 가공 후 현미경 계측)]
  Kerf  [μm]: Film 표면상 가공 폭
  Depth [μm]: Film의 잔존 두께
  최종 판정:
    미가공 : Depth > 25μm
    OK     : 0 < Depth ≤ 25μm  ← AI 목표
    과가공 : Depth = 0μm (완전 관통)
    NG     : Defect 감지 시
```

### 1.2 Excel 두 시트 관계 (추측 확정)

**결론: Data 시트와 Sheet1은 동일한 328개 실험의 컬럼 분리 저장입니다.**

근거:
- Slide 3 테이블에서 하나의 행이 `No. | Sample | Process | LASER | Sensor | Result` 전부 포함
- Data 시트: `No. / M1 / M1 length / M2 / M2 length / Thickness / Speed / Defocus` (Sample + Process)
- Sheet1: `Frequency / Power / Data 유무 / Kerf / Depth / 최종` (LASER + Sensor + Result)
- 두 시트 모두 328건으로 동일 → **행 순서 기준 1:1 조인**

```
Data 시트 행 1 (No.1, Glass, 10, Film, 25, 111.8, 500, 0)
         +
Sheet1 행 1    (200, 6.0, 공백, 78.3, 95.0, 미가공)
         ↓
통합 행: No.1 | Glass | 10 | Film | 25 | 111.8μm | Speed=500 | Defocus=0
              | Freq=200kHz | Power=6W | 센서OK | Kerf=78.3μm | Depth=95.0μm | 미가공
```

### 1.3 전체 데이터 현황

| 구분 | 내용 |
|---|---|
| 총 실험 번호 | 355개 (No.1~355) |
| 결측 행 | 34개 (No.41~51 외) |
| **실유효 데이터** | **328건** |
| 품질 분포 | OK: 45건(13.7%) / 미가공: 159건(48.5%) / 과가공: 124건(37.8%) |
| 센서 데이터 없음 | 7건 (Power 낮아 Plasma Threshold 미달) |
| Plasma 시계열 | 별도 ZIP 파일 (CSV, 250kHz, 0.1초 기록) |

> **OK 13.7%** — 이것이 Bayesian Optimization이 필요한 이유입니다.
> 수동으로는 이 좁은 OK 구간을 찾기 위해 수십 번 실험이 필요합니다.

### 1.4 판정 기준 (Slide 7에서 확인)

| 판정 | 기준 |
|---|---|
| 미가공 | Depth > 25μm |
| **OK** | **0μm < Depth ≤ 25μm** |
| 과가공 | Depth = 0μm |
| NG | Defect 감지 시 |

---

## 2. 기술 스택 및 포트 확정

### 2.1 rag-pm-matcher 포트 충돌 분석

```
기존 점유 포트: 80, 2222, 3000, 3001, 3002, 3003, 6333, 8000, 8080, 9090, 11434

AI-ADES 신규 할당:
  8010 → data-prep-agent FastAPI
  8011 → modeling-agent FastAPI
  8012 → execution-agent FastAPI
  5173 → React 프론트엔드 (Vite dev server)
  5000 → MLflow UI
  8086 → InfluxDB
  9092 → Kafka (내부 전용, 호스트 미노출)
  3010 → Grafana AI-ADES 전용 (기존 3002와 분리)

공유 사용 (기존 컨테이너):
  11434 → Ollama (Qwen/Claude/ChatGPT 멀티 프로바이더)
  5432  → PostgreSQL (ades_db 스키마 신규 추가)
  6333  → Qdrant (ades_ 접두사 컬렉션 분리)
```

### 2.2 Surface 32GB 메모리 예산

```
OS + 기타                : 6.0 GB
Ollama Qwen2.5:14b       : 8.0 GB  ← 공유
PostgreSQL (기존)         : 0.5 GB  ← 공유
Qdrant (기존)             : 0.5 GB  ← 공유
InfluxDB                 : 0.5 GB
Kafka (경량: Xmx512m)     : 0.6 GB
MLflow                   : 0.3 GB
Grafana                  : 0.3 GB
AI-ADES 3개 Agent        : 2.0 GB
React Dev                : 0.5 GB
XGBoost 학습 피크         : 2.0 GB
─────────────────────────────────
합계                    : ~21 GB  ✓ 32GB 여유
```

---

## 3. 스키마 정의 (PPT + Excel 완전 반영)

### 3.1 통합 실험 테이블

```sql
CREATE TABLE experiments (
  id              SERIAL PRIMARY KEY,
  exp_no          VARCHAR(20) UNIQUE,     -- 실험 번호 (1, 2, ..., 300-2 등)

  -- Sample (소재 정보)
  m1_material     VARCHAR(50) DEFAULT 'Glass',
  m1_length       FLOAT,                  -- 4 / 10 / 20 mm
  m2_material     VARCHAR(50) DEFAULT 'Film',
  m2_length       FLOAT,                  -- 10 / 25 / 50 mm
  thickness       FLOAT,                  -- Film 실측 두께 [μm]

  -- Process (모터 파라미터)
  speed           FLOAT,                  -- 200 / 500 / 1000 mm/s
  defocus         FLOAT,                  -- 0 / 1 / 2 / 3 / 4 mm

  -- Laser (레이저 파라미터)
  frequency       FLOAT,                  -- 100 / 200 kHz
  power           FLOAT,                  -- 2.8 ~ 59.8 W

  -- Sensor
  sensor_data_ok  BOOLEAN DEFAULT TRUE,   -- FALSE = 'X' (Plasma 미감지)

  -- Result (현미경 계측)
  kerf            FLOAT,                  -- 가공 폭 [μm]
  depth           FLOAT,                  -- 잔존 두께 [μm]
  quality         VARCHAR(20),            -- '미가공' / 'OK' / '과가공' / 'NG'
  quality_score   INT,                    -- OK=1, 미가공=0, 과가공=-1, NG=-2

  -- 메타
  data_source     VARCHAR(50) DEFAULT 'excel_poc',
  created_at      TIMESTAMP DEFAULT NOW()
);
```

### 3.2 Plasma 시계열 테이블 (ZIP 데이터용)

```sql
CREATE TABLE plasma_timeseries (
  id              SERIAL PRIMARY KEY,
  exp_no          VARCHAR(20),
  config_id       INT,                    -- Plasma 센서 ConfigID
  measurement_id  INT,                    -- MeasurementID
  duration        FLOAT,                  -- 측정 시간 [s] (0.1s)
  sample_rate     INT,                    -- 250000 Hz
  region          VARCHAR(10),            -- 'M1' / 'M2' / 'Blank'

  -- 시계열 배열 (JSON 저장 또는 별도 행)
  time_idx        INT,
  time_sec        FLOAT,
  area            FLOAT,
  plasma          FLOAT,
  p_raw           FLOAT,
  temp            FLOAT,
  t_raw           FLOAT,
  refl            FLOAT,
  r_raw           FLOAT,

  FOREIGN KEY (exp_no) REFERENCES experiments(exp_no)
);
```

### 3.3 레시피 테이블

```sql
CREATE TABLE recipes (
  id              SERIAL PRIMARY KEY,
  m1_length       FLOAT,
  m2_length       FLOAT,
  target_quality  VARCHAR(20) DEFAULT 'OK',

  -- AI 추천 최적 파라미터
  opt_speed       FLOAT,
  opt_defocus     FLOAT,
  opt_frequency   FLOAT,
  opt_power       FLOAT,

  -- 예측값
  pred_kerf       FLOAT,
  pred_depth      FLOAT,
  confidence      FLOAT,                  -- 신뢰도 %
  pred_quality    VARCHAR(20),

  -- 검증
  r2_score        FLOAT,
  doe_attempts    INT,                    -- 몇 번 만에 수렴했는지
  approved_by     VARCHAR(100),
  approved_at     TIMESTAMP,
  created_at      TIMESTAMP DEFAULT NOW()
);
```

### 3.4 Bayesian Optimization 탐색 공간

```python
# 실험 데이터 기반 완전 확정된 탐색 공간
SEARCH_SPACE = {
    "speed":      {"type": "discrete", "values": [200, 500, 1000]},  # mm/s
    "defocus":    {"type": "discrete", "values": [0, 1, 2, 3, 4]},   # mm
    "frequency":  {"type": "discrete", "values": [100, 200]},         # kHz
    "power":      {"type": "continuous", "range": [2.8, 59.8]},       # W
}

# 목표 함수: depth가 0 < depth ≤ 25μm 범위에 들도록
# = quality_score 최대화 (OK=1 달성)
# 제약: depth > 0 (과가공 방지)

# OK 구간이 13.7%로 좁기 때문에
# Bayesian Opt의 "좁은 범위를 적은 실험으로 수렴"하는 특성이 핵심 가치
```

---

## 4. Feature Engineering 설계

```python
# 기본 변수 (4개)
base_features = ['speed', 'defocus', 'frequency', 'power']

# 소재 변수 (2개)
material_features = ['m1_length', 'm2_length', 'thickness']

# 파생 변수 (물리적 의미 있는 조합)
derived = {
    'energy_density':      power / speed,          # 에너지 밀도 (W·s/mm)
    'power_x_defocus':     power × defocus,         # 출력-초점 교호작용
    'freq_x_power':        frequency × power,       # 주파수-출력 교호작용
    'thickness_ratio':     m1_length / m2_length,  # 소재 비율
    'normalized_power':    power / (speed / 1000), # 속도 정규화 출력
}

# SHAP 분석 예상: Power가 가장 영향력 높을 것
# (실험 데이터 패턴: Power 증가 → depth 감소 → 과가공 위험)
```

---

## 5. Phase별 개발 계획

### Phase 0 — 환경 세팅 (3~4일)

**목표**: rag-pm-matcher와 충돌 없이 AI-ADES Docker 환경 구동

```
작업 목록:
□ D:\Claude\ai-ades 프로젝트 생성
□ CLAUDE.md 작성 (Claude Code용 작업 지시서)
□ docker-compose.yml 작성
  - PostgreSQL, Qdrant, Ollama: 기존 네트워크 참조 (신규 컨테이너 불필요)
  - InfluxDB:8086, MLflow:5000, Grafana:3010, Kafka:9092 신규 추가
  - Kafka 힙 메모리 제한: KAFKA_HEAP_OPTS="-Xmx512m"
□ .env 파일 작성 (포트 충돌 완전 회피 설정)
□ PostgreSQL에 ades_db 스키마 생성 (기존 pmdb와 분리)
□ schema.sql 실행 → 3개 테이블 생성
□ 전체 서비스 docker-compose up 확인
  - http://localhost:3010 → Grafana
  - http://localhost:5000 → MLflow
  - http://localhost:8086 → InfluxDB
```

**완료 기준**: 5개 서비스 정상 기동, 포트 충돌 없음 확인

---

### Phase 1 — Data Preparation Agent (4~5일)

**목표**: Excel 328건 통합 파싱 → DB 적재 → InfluxDB 시계열 저장

```
작업 목록:
□ Excel 통합 파서
  - Data 시트 + Sheet1 → 행 순서 기준 1:1 조인
  - exp_no 비정형 처리 ('300-2' 등)
  - quality_score 파생: OK=1, 미가공=0, 과가공=-1, NG=-2
  - 이상값 2건 처리: Thickness 144.5μm, 177.5μm → 플래그 처리
□ PostgreSQL experiments 테이블 적재 (328건)
□ InfluxDB 적재: 실험 결과를 시계열로 저장
  (Plasma 시계열 ZIP은 Phase 6에서 처리 — 고객사 현장에서 실제 데이터로)
□ FastAPI 엔드포인트:
  POST /data/upload   → Excel 파일 업로드 → 자동 파싱·적재
  GET  /data/summary  → 전체 데이터 현황 요약
  GET  /data/distribution → 품질 분포 조회
□ Grafana 패널 구성:
  - 소재 조합별 OK/미가공/과가공 분포 차트
  - Speed × Power 히트맵 (OK 구간 시각화)
  - Defocus × Power 히트맵
```

**완료 기준**: Excel 업로드 → Grafana에서 품질 분포 확인 가능

---

### Phase 2 — Modeling Agent (5~6일)

**목표**: XGBoost 모델 3개 + SHAP 분석 + MLflow 연동

```
작업 목록:

[XGBoost 모델 3개]
□ kerf_model   : 가공 폭(Kerf) 회귀 예측
□ depth_model  : 잔존 두께(Depth) 회귀 예측 ← 가장 중요
□ quality_model: 판정 분류 (4클래스: OK/미가공/과가공/NG)
  - 클래스 불균형 처리: OK(45건) 가중치 UP
  - scale_pos_weight 설정

□ Feature Engineering 파이프라인
  - energy_density, power_x_defocus 등 파생 변수 생성

□ Optuna 100회 하이퍼파라미터 최적화 (CPU, n_jobs=-1)
□ K-Fold 교차검증 (k=5) + Hold-out 20%
□ MLflow 실험 자동 기록 (파라미터, 메트릭, 모델 아티팩트)

[SHAP 분석]
□ TreeExplainer → 파라미터 영향도 순위
□ 예상 결과: Power > Speed > Defocus > Frequency 순
□ JSON 포맷으로 FastAPI 응답에 포함

[LLM 연동 — SHAP 설명 자연어화]
□ Ollama(Qwen) 기본 / Claude API / ChatGPT 선택 가능
□ 프롬프트: "SHAP 분석 결과 {shap_dict}를 보고
  '{m1_length}mm + {m2_length}mm 소재에서 OK를 내려면
  어떤 파라미터를 어떻게 조정해야 하는지 운영자에게 설명해줘'"

[FastAPI 엔드포인트]
□ POST /model/train  → 학습 실행
□ POST /predict      → 예측 요청
  Input:  {speed, defocus, frequency, power, m1_length, m2_length, thickness}
  Output: {pred_kerf, pred_depth, pred_quality, confidence, shap_values,
           llm_explanation}
□ GET  /model/status → 현재 모델 R² / F1 현황
```

**완료 기준**: R² ≥ 0.75 (불균형 데이터·소규모 감안), OK 클래스 F1 ≥ 0.60

---

### Phase 3 — Execution Agent + Auto DOE (4~5일)

**목표**: Bayesian Opt Auto DOE + 레시피 DB + 승인 토큰 시스템

```
작업 목록:

[Bayesian Optimization Auto DOE]
□ BoTorch GP 기반 구현
□ 이산 변수 처리:
  - speed, defocus, frequency → 반올림 후 유효값 스냅
  - power → 연속 탐색
□ 이전 실험 결과 → GP 업데이트 로직
□ 획득 함수: Expected Improvement (EI) — OK 달성 확률 최대화
□ 제약: depth_pred > 0 (과가공 방지)

[FastAPI 엔드포인트]
□ POST /doe/suggest   → 다음 실험 조건 제안
  Input:  {m1_length, m2_length, thickness, experiment_history, n_suggestions}
  Output: {suggested_params, pred_depth, pred_quality, confidence,
           shap_explanation, llm_explanation}
□ POST /doe/approve   → 운영자 승인 + 레시피 저장
  Input:  {suggestion_id, operator_name}
  Output: {approval_token, recipe_id}
□ POST /doe/reject    → 거부 + 이유 기록
□ GET  /recipes       → 저장된 레시피 목록
□ GET  /recipes/{m1_length}/{m2_length} → 소재별 최적 레시피 조회

[LLM 전환 테스트]
□ .env LLM_PROVIDER=ollama / claude / openai 전환 확인
```

**완료 기준**: Glass 10mm + Film 25mm 조건에서
Auto DOE 5~7회 내 OK 수렴 시뮬레이션 성공

---

### Phase 4 — 운영자 UI + E2E 통합 (4~5일)

**목표**: React 승인 화면 3개 + Grafana 완성 + E2E 테스트

```
[React 화면 3개]

1. 실험 조건 입력 화면
   - 소재 선택: M1 length (4/10/20), M2 length (10/25/50)
   - Thickness 실측값 입력
   - [Auto DOE 시작] 버튼

2. AI 파라미터 제안 + 승인 화면 (가장 중요)
   ┌─────────────────────────────────────┐
   │  AI 제안 파라미터                    │
   │  Speed: 500 mm/s  Defocus: 1 mm    │
   │  Freq:  200 kHz   Power:  15.2 W   │
   ├─────────────────────────────────────┤
   │  예측 결과                           │
   │  Kerf: 155μm  Depth: 18.4μm        │
   │  판정: OK  신뢰도: 87%              │
   ├─────────────────────────────────────┤
   │  SHAP 영향도 (Recharts 막대)         │
   │  Power ████████████ 44%             │
   │  Speed ████████ 28%                 │
   │  Defocus █████ 18%                  │
   ├─────────────────────────────────────┤
   │  AI 설명 (LLM)                      │
   │  "Power 15.2W에서 OK 확률이 87%     │
   │   입니다. Speed 500에서 Defocus 1   │
   │   이 최적 조합으로 분석됩니다."      │
   ├─────────────────────────────────────┤
   │  [✓ 승인]  [✎ 수정 후 승인]  [✗ 거부] │
   └─────────────────────────────────────┘

3. 결과 보고 화면
   - Auto DOE 실험 이력 테이블
   - DOE 수렴 그래프 (depth 변화 추이)
   - OK 달성 레시피 저장 현황

[Grafana 완성]
□ 실험 현황 패널 (InfluxDB)
□ Speed × Power OK 구간 히트맵
□ DOE 수렴 이력 그래프

[E2E 테스트]
□ Excel 업로드 → 모델 학습 → DOE 제안 → 승인 → 결과 저장 전 루프 3회
□ LLM 3종 전환 테스트 (Qwen / Claude API / ChatGPT)
```

**완료 기준**: Surface에서 E2E 루프 3회 오류 없이 완주

---

#### Phase 4 실제 구현 현황 (계획 대비 확장, 2026-06-13 기준)

> 아래는 위 계획(화면 3개 + Grafana + E2E) 대비 **실제로 추가 구현된 범위**다.
> 원 계획 서술은 보존하고, 구현 결과만 별도로 정리한다. (상태: API 레벨 E2E 완료, 화면 UI 다듬기 마무리 단계)

**1. 운영자 UI — 계획 3개 화면 + 추가 화면**
- (계획) 실험 조건 입력 / AI 제안·승인 / 결과 보고 — 3개 모두 구현 완료
- (추가) **레시피 조회**(`/recipes`), **실험 이력 조회**(`/history`), **AI 채팅**(`/chat`, 채팅 이력 관리 포함)

**2. 실험 조건 입력 — 확장**
- 소재 **종류** 선택(M1/M2 종류, 관리자 콘솔에서 등록한 소재) — 고정 4/10/20을 넘어 자유 입력 + 프리셋
- **외삽 경고**: 입력값이 학습 데이터 범위를 벗어나면 신뢰도 저하 경고 표시
- **검증된 레시피 "1회 확인 실험"** 흐름(Thickness 일치 레시피 보유 시 바로 승인 화면으로)

**3. AI 제안·승인 — 확장**
- SHAP 영향도 그래프(파생변수 포함, 라벨 영어 통일), 수정 후 재예측(`/doe/repredict`), 거부 사유 입력 모달
- LLM 설명 백그라운드 비동기 생성(`/doe/explanation`)

**4. 결과 보고 — 확장**
- **AI 평가**(실측값 기반 LLM 보고 초안, `/doe/evaluate`)
- **결과 저장 확인 모달** + **사전 판정 미리보기**(`/doe/criteria`로 기준 수신, 하드코딩 금지)
- Auto DOE 수렴 이력 테이블

**5. 관리자 콘솔(Admin Console) — 계획에 없던 신규(10개 섹션)**
- 시스템 상태(헬스체크·모델지표·리소스) / 서비스 관리(컨테이너 재시작) / **LLM 모델 선택·전환**(멀티 프로바이더) / 모델 재학습 + **자동 재학습 진행도**(50건 누적) / **판정 기준·탐색 공간 설정**(.env 즉시 반영) / **소재 종류 관리**(CRUD) / 사용자 관리 / 알림 설정 / 감사 로그 / **데이터 관리**(DB 백업 pg_dump·experiments CSV·**테스트 데이터 정리**(판정/생성시각 필터))

**미반영(계획에는 있으나 후속)**: Grafana 패널 3종(실험현황/OK 히트맵/수렴 그래프)은 인프라만 기동, 패널 구성은 Phase 6 실데이터 단계에서 마무리 예정. LLM 3종 전환은 프로바이더 전환 기능으로 구현(실 API 키 연결 테스트는 고객사 정책 확정 후).

---

### Phase 5 — 고객사 설치 테스트 (현장)

**목표**: 고객 워크스테이션 2대 설치 + GPU 환경 검증

```
사전 준비:
□ docker-compose.prod.yml (GPU_ENABLED=true 옵션)
□ install.bat (Windows 원클릭 설치)
□ env.check.py (CUDA 확인 / 포트 충돌 / 메모리 점검)

[설계해석 워크스테이션: Xeon W5-2545 + RTX PRO 4000 Blackwell]
□ NVIDIA Driver 570+ 확인
□ Docker GPU 패스스루 (NVIDIA Container Toolkit)
□ PyTorch GPU 모드로 재컴파일 (LSTM 학습 속도 향상)
□ 전체 docker-compose.prod.yml 기동
□ GPU 인식 확인 (nvidia-smi)

[CPU특화 워크스테이션: ULTRA 9 285]
□ Kafka / InfluxDB / PostgreSQL 전담
□ 두 워크스테이션 간 내부 네트워크 연결 확인

□ Excel POC 데이터로 Phase 1~4 재검증
```

**완료 기준**: 고객사 H/W에서 E2E 루프 3회 완주

---

### Phase 6 — 설비 연동 (고객사 현장)

**목표**: 실제 CO₂ 레이저 설비 연동 + Plasma 시계열 학습 + 실시간 운영

```
현장 실사 확인 사항:
□ 레이저 설비 통신 인터페이스 종류
  (OPC-UA / RS-232 / Ethernet / 설비 전용 API)
□ 실시간으로 읽을 수 있는 파라미터 목록
  (Speed / Defocus / Frequency / Power 실시간 노출 여부)
□ 가공 완료 후 Kerf / Depth 자동 측정 장치 유무
  (없으면 운영자 수동 입력 UI 필요 → 이미 승인 화면에 포함)
□ Plasma sensor ZIP 데이터 포맷 확인
  (250kHz CSV, Index;Time;Area;Plasma;P-Raw;Temp;T-Raw;Refl;R-Raw)
□ 공장 네트워크 IP 대역 / 방화벽 포트 허용

작업 목록:
□ 설비 통신 드라이버 개발 (OPC-UA 또는 해당 프로토콜)
□ Plasma sensor ZIP 파서 → plasma_timeseries 테이블 적재
□ LSTM-Autoencoder 학습 (Plasma 시계열 기반 이상감지)
  - M1/M2/Blank 구간 자동 분리
  - 정상 패턴 학습 → F1 ≥ 0.80 목표
□ 실데이터 기반 모델 재학습
  (POC Excel → 실설비 데이터로 점진 교체)
□ Airflow DAG: 50건 누적 → 자동 재학습 트리거
□ 24시간 연속 수집 테스트
□ 납품 시연 리허설 3회 → 최종 시연
```

**완료 기준**: 실설비 Auto DOE 5~7회 내 OK 수렴 실증, 납품 시연 완료

---

## 6. 프로젝트 디렉토리 구조

```
D:\Claude\ai-ades\
├── CLAUDE.md
├── docker-compose.yml          ← 로컬 개발 (Surface)
├── docker-compose.prod.yml     ← 고객사 설치 (GPU 포함)
├── .env                        ← 환경변수 (포트 충돌 회피)
├── .env.example
│
├── services/
│   ├── data-prep-agent/        ← Port 8010
│   │   ├── main.py
│   │   ├── excel_parser.py     ← Data+Sheet1 행순서 조인
│   │   ├── preprocessor.py     ← quality_score, 이상값 처리
│   │   ├── influx_writer.py    ← InfluxDB 적재
│   │   └── plasma_parser.py    ← ZIP CSV 파서 (Phase 6)
│   │
│   ├── modeling-agent/         ← Port 8011
│   │   ├── main.py
│   │   ├── feature_engineering.py
│   │   ├── xgboost_pipeline.py ← kerf/depth/quality 3모델
│   │   ├── lstm_model.py       ← Plasma 시계열 (Phase 6)
│   │   ├── shap_analyzer.py
│   │   ├── optuna_tuner.py
│   │   └── mlflow_tracker.py
│   │
│   ├── execution-agent/        ← Port 8012
│   │   ├── main.py
│   │   ├── bayesian_opt.py     ← BoTorch Auto DOE
│   │   ├── recipe_db.py
│   │   ├── approval.py
│   │   └── llm_explainer.py    ← Ollama/Claude/ChatGPT
│   │
│   └── monitoring/
│       └── grafana/dashboards/
│
├── frontend/                   ← Port 5173
│   └── src/pages/
│       ├── ExperimentPage.jsx  ← 조건 입력
│       ├── ApprovalPage.jsx    ← 제안 승인 (핵심)
│       └── ResultPage.jsx      ← 결과 보고
│
└── data/
    ├── raw/AI-ADES_POC_data_condition_results.xlsx
    └── schema/schema.sql
```

---

## 7. .env 설정 (최종)

```bash
# ── LLM (기존 Ollama 공유) ──
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:14b
CLAUDE_API_KEY=
OPENAI_API_KEY=

# ── DB (기존 PostgreSQL 공유, DB명 분리) ──
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=ades_db            # pmdb와 분리
POSTGRES_USER=ades
POSTGRES_PASSWORD=ades

# ── 신규 서비스 ──
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=ades-secret-token
INFLUXDB_ORG=ades
INFLUXDB_BUCKET=laser_process
MLFLOW_TRACKING_URI=http://localhost:5000
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION_PREFIX=ades_

# ── AI-ADES 포트 (충돌 회피 완료) ──
DATA_PREP_PORT=8010
MODELING_PORT=8011
EXECUTION_PORT=8012
FRONTEND_PORT=5173
GRAFANA_PORT=3010

# ── 공정 설정 ──
QUALITY_TARGET=OK
DEPTH_OK_MIN=0.0               # μm (초과)
DEPTH_OK_MAX=25.0              # μm (이하)
ENV=development
GPU_ENABLED=false              # Surface: GPU(RTX 3050 Ti) 탑재되어 있으나 개발 단계는 false, 고객사: true
```

---

## 8. 일정 요약

| Phase | 내용 | 기간 | 장소 |
|---|---|---|---|
| Phase 0 | 환경 세팅, DB 스키마 | 3~4일 | Surface |
| Phase 1 | Data Prep Agent, Excel 파싱 | 4~5일 | Surface |
| Phase 2 | Modeling Agent, XGBoost+SHAP | 5~6일 | Surface |
| Phase 3 | Execution Agent, Bayesian Opt | 4~5일 | Surface |
| Phase 4 | React UI + E2E 통합 | 4~5일 | Surface |
| **로컬 합계** | **프로토 완성** | **약 4~5주** | |
| Phase 5 | 고객사 설치, GPU 환경 검증 | 별도 | 고객사 |
| Phase 6 | 설비 연동, Plasma 시계열, 재학습 | 별도 | 고객사 |

---

## 9. 착수 즉시 가능 — 확인 불필요한 것들

PPT + Excel 완전 분석 완료로 아래는 고객 확인 없이 진행합니다.

| 항목 | 결정 내용 |
|---|---|
| 두 시트 관계 | 행 순서 기준 1:1 조인 |
| 판정 기준 | OK = 0 < Depth ≤ 25μm |
| 입력 변수 | Speed/Defocus/Frequency/Power + 소재 정보 |
| 탐색 공간 | Speed:200/500/1000, Defocus:0~4, Freq:100/200, Power:2.8~59.8 |
| PostgreSQL | 기존 컨테이너 공유, ades_db 스키마 신규 |
| Grafana | 포트 3010 (기존 3002와 분리) |
| LSTM 시계열 | Phase 6까지 후순위 (Plasma ZIP은 고객사 현장에서 처리) |

**착수 지시를 주시면 Phase 0부터 바로 시작합니다.**

---

## 10. 향후 개선 (백로그)

> 기본 기능 완성 후 보완할 항목. 우선순위는 고객사 운영 피드백에 따라 조정. (2026-06-14 기준)

| 항목 | 내용 | 착수 시점 |
|---|---|---|
| **AI 채팅 매뉴얼 RAG 전환** | 현재 AI 채팅은 `system_manual.md` **전체**를 매 요청마다 프롬프트에 통째로 주입(in-context, RAG 아님). 매뉴얼이 커지면 응답 지연·컨텍스트 한계 발생 → 매뉴얼을 임베딩해 **질문과 관련된 부분만 검색·주입하는 RAG**로 전환. 기존 Qdrant 컨테이너(ades_ 접두사 컬렉션) 활용 가능 | 매뉴얼이 수십 KB로 커지는 시점 (그 전까지는 in-context로 충분) |
| Grafana 패널 구성 | 실험현황 / Speed×Power OK 히트맵 / DOE 수렴 그래프 패널 (인프라·InfluxDB는 기동 완료, 패널만 미구성) | Phase 6 실데이터 단계 |
| 승인 화면 수정입력 탐색공간 가드 | 운영자 수정값이 SEARCH_SPACE를 벗어나지 못하도록 이산값 드롭다운 / Power 2.8~59.8 범위 검증 | 선택 |
| 매뉴얼 즉시 반영(개발 편의) | `system_manual.md` 볼륨 마운트 + 요청마다 재읽기로 재빌드 없이 반영 (RAG 전환 시 함께 정리 가능) | 선택 |
