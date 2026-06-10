# AI-ADES CLAUDE.md
## AI Autonomous Data Evaluation System — Claude Code 작업 지침서

> 이 파일은 Claude Code CLI가 자동으로 읽는 프로젝트 헌법입니다.
> 모든 작업은 이 지침을 우선 따릅니다.
> 수정이 필요하면 claude.ai 채팅에서 요청하세요.

---

## 1. 프로젝트 개요

### 무엇을 만드는가
CO₂ 레이저로 Glass + Film 적층 소재를 절단할 때,
AI가 최적 레이저 조건을 자동으로 찾아주는 시스템.

### 핵심 목표
- 수동으로 30~50번 필요했던 실험을 **5~7번으로 단축**
- OK 판정 달성: **0μm < Depth ≤ 25μm**
- 운영자는 [승인] 버튼만 누르면 됨 (Human-in-the-Loop)

### 3단계 배포 계획
```
1단계: Surface Laptop Studio 1 (개발·테스트, 지금)
2단계: 고객사 워크스테이션 2대 (설치 테스트)
3단계: 고객사 CO₂ 레이저 설비 연동 (실운영)
```

---

## 2. 기술 스택

### 기존 rag-pm-matcher에서 공유 (새로 띄우지 않음)
| 서비스 | 포트 | 용도 |
|---|---|---|
| PostgreSQL | 5432 (내부) | ades_db 스키마 신규 추가 |
| Qdrant | 6333 | ades_ 접두사 컬렉션 분리 |
| Ollama | 11434 | LLM 추론 (Qwen2.5:14b) |

### AI-ADES 신규 서비스
| 서비스 | 포트 | 용도 |
|---|---|---|
| data-prep-agent | 8010 | FastAPI, 데이터 수집·전처리 |
| modeling-agent | 8011 | FastAPI, AI 모델 학습·예측 |
| execution-agent | 8012 | FastAPI, Auto DOE·승인·레시피 |
| frontend | 5173 | React + Vite, 운영자 UI |
| InfluxDB | 8086 | 시계열 데이터 저장 |
| MLflow | 5000 | 모델 실험 관리 |
| Grafana | 3010 | 실시간 모니터링 (3002 사용 금지) |
| Kafka | 9092 | 내부 전용, 호스트 미노출 |

### AI/ML 라이브러리
```
xgboost, scikit-learn, shap, optuna   ← 품질 예측
torch (CPU 모드), botorch              ← 이상감지, Auto DOE
mlflow                                 ← 실험 관리
influxdb-client                        ← 시계열 DB
kafka-python                           ← 데이터 파이프라인
```

### LLM 멀티 프로바이더 (기존 rag-pm-matcher 패턴 재활용)
```python
LLM_PROVIDER=ollama   # 기본 (로컬, 무료)
LLM_PROVIDER=claude   # Claude API
LLM_PROVIDER=openai   # ChatGPT API
# .env의 LLM_PROVIDER 값으로 런타임 전환
```

---

## 3. 디렉토리 구조

```
D:\Claude\ai-ades\
├── CLAUDE.md                      ← 이 파일
├── docker-compose.yml             ← 로컬 개발용
├── docker-compose.prod.yml        ← 고객사 설치용 (GPU 포함)
├── .env                           ← 환경변수 (절대 git push 금지)
├── .env.example                   ← 환경변수 템플릿
├── .gitignore
│
├── services/
│   ├── data-prep-agent/           ← Port 8010
│   │   ├── main.py
│   │   ├── excel_parser.py        ← Data+Sheet1 행순서 조인
│   │   ├── preprocessor.py        ← quality_score 파생, 이상값 처리
│   │   ├── influx_writer.py       ← InfluxDB 적재
│   │   └── plasma_parser.py       ← Plasma CSV (Phase 6)
│   │
│   ├── modeling-agent/            ← Port 8011
│   │   ├── main.py
│   │   ├── feature_engineering.py
│   │   ├── xgboost_pipeline.py    ← kerf/depth/quality 3개 모델
│   │   ├── lstm_model.py          ← Plasma 시계열 (Phase 6)
│   │   ├── shap_analyzer.py
│   │   ├── optuna_tuner.py
│   │   └── mlflow_tracker.py
│   │
│   ├── execution-agent/           ← Port 8012
│   │   ├── main.py
│   │   ├── bayesian_opt.py        ← BoTorch Auto DOE
│   │   ├── recipe_db.py
│   │   ├── approval.py
│   │   └── llm_explainer.py       ← LLM 멀티 프로바이더
│   │
│   └── monitoring/
│       └── grafana/dashboards/
│
├── frontend/                      ← Port 5173
│   └── src/pages/
│       ├── ExperimentPage.jsx     ← 조건 입력
│       ├── ApprovalPage.jsx       ← AI 제안 승인 (핵심 화면)
│       └── ResultPage.jsx         ← 결과 보고
│
└── data/
    ├── raw/                       ← 원본 Excel (변경 금지)
    └── schema/schema.sql          ← DB 스키마
```

---

## 4. 데이터 구조 (핵심 지식)

### Excel POC 데이터 구조
```
파일: AI-ADES_POC_data_condition_results.xlsx
총 데이터: 328건 (No.1~355 중 결측 34건 제외)

Data 시트 (Sample + Process):
  No. / M1(Glass) / M1 length(4·10·20mm) / M2(Film) /
  M2 length(10·25·50mm) / Thickness(μm) / Speed(200·500·1000) / Defocus(0~4)

Sheet1 (Laser + Sensor + Result):
  Frequency(100·200kHz) / Power(2.8~59.8W) / Data유무(X=센서없음) /
  Kerf(μm) / Depth(μm) / 최종(미가공·OK·과가공·NG)

⚠ 두 시트는 행 순서 기준 1:1 조인 (No.1행 = Sheet1 1행)
```

### 판정 기준 (절대 변경 금지)
```python
# .env의 값을 사용할 것 (하드코딩 금지)
DEPTH_OK_MIN = 0.0    # μm 초과
DEPTH_OK_MAX = 25.0   # μm 이하
# 미가공: depth > 25μm
# OK    : 0 < depth ≤ 25μm  ← AI의 목표
# 과가공: depth = 0μm
# NG    : Defect 감지
```

### Bayesian Optimization 탐색 공간
```python
SEARCH_SPACE = {
    "speed":     {"type": "discrete", "values": [200, 500, 1000]},
    "defocus":   {"type": "discrete", "values": [0, 1, 2, 3, 4]},
    "frequency": {"type": "discrete", "values": [100, 200]},
    "power":     {"type": "continuous", "range": [2.8, 59.8]},
}
# 탐색 공간 외 값은 절대 제안하지 않음
```

### quality_score 매핑
```python
QUALITY_SCORE = {"OK": 1, "미가공": 0, "과가공": -1, "NG": -2}
```

---

## 5. 서버 실행 명령

```bash
# 전체 서비스 기동
docker-compose up -d

# 개별 서비스 재시작
docker-compose restart data-prep-agent
docker-compose restart modeling-agent
docker-compose restart execution-agent

# 로그 확인
docker-compose logs -f modeling-agent

# 각 Agent 개발 모드 실행 (컨테이너 밖에서)
cd services/data-prep-agent  && uvicorn main:app --reload --port 8010
cd services/modeling-agent   && uvicorn main:app --reload --port 8011
cd services/execution-agent  && uvicorn main:app --reload --port 8012

# 프론트엔드
cd frontend && npm run dev

# DB 스키마 초기화
psql -h localhost -U ades -d ades_db -f data/schema/schema.sql

# MLflow UI 확인
http://localhost:5000

# Grafana 확인 (3002 아님! 3010)
http://localhost:3010
```

---

## 6. 환경변수 (.env 필수 항목)

```bash
# LLM
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:14b
CLAUDE_API_KEY=
OPENAI_API_KEY=

# DB
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=ades_db
POSTGRES_USER=ades
POSTGRES_PASSWORD=ades

# InfluxDB
INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=ades-secret-token
INFLUXDB_ORG=ades
INFLUXDB_BUCKET=laser_process

# MLflow
MLFLOW_TRACKING_URI=http://localhost:5000

# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION_PREFIX=ades_

# 포트
DATA_PREP_PORT=8010
MODELING_PORT=8011
EXECUTION_PORT=8012
FRONTEND_PORT=5173
GRAFANA_PORT=3010

# 공정 판정 기준
DEPTH_OK_MIN=0.0
DEPTH_OK_MAX=25.0

# 환경
ENV=development
GPU_ENABLED=false
```

---

## 7. 코딩 규칙

### 필수 규칙
```python
# 1. 한국어 주석 필수
def predict_quality(features: dict) -> dict:
    """
    레이저 가공 품질 예측
    Args: features - 입력 파라미터 (speed, defocus, frequency, power 등)
    Returns: 예측 결과 (pred_depth, pred_quality, confidence, shap_values)
    """
    # XGBoost 모델로 Depth 예측
    pred_depth = depth_model.predict(...)

# 2. 환경변수는 반드시 .env에서 읽기
from dotenv import load_dotenv
DEPTH_OK_MAX = float(os.getenv("DEPTH_OK_MAX", 25.0))  # 하드코딩 금지

# 3. 판정 기준 함수화 (여러 곳에서 직접 비교 금지)
def judge_quality(depth: float) -> str:
    if depth > DEPTH_OK_MAX:   return "미가공"
    if depth == 0.0:           return "과가공"
    if depth <= DEPTH_OK_MAX:  return "OK"
    return "NG"

# 4. API 응답 형식 통일
return {
    "success": True,
    "data": {...},
    "message": "예측 완료"
}
```

### FastAPI 엔드포인트 명명 규칙
```
POST /data/upload          ← Excel 업로드
GET  /data/summary         ← 데이터 현황
POST /model/train          ← 모델 학습
POST /predict              ← 예측 요청
POST /doe/suggest          ← Auto DOE 제안
POST /doe/approve          ← 운영자 승인
POST /doe/reject           ← 거부
GET  /recipes              ← 레시피 조회
GET  /health               ← 서비스 상태
```

### 금지 사항
```
✗ 판정 기준값(0, 25) 하드코딩
✗ API Key 코드에 직접 입력
✗ Grafana 포트 3002 사용 (3010만 사용)
✗ 기존 rag-pm-matcher 컨테이너 수정
✗ PostgreSQL pmdb 스키마 수정 (ades_db만 사용)
✗ 파일 한 개에 500줄 이상 작성 (분리할 것)
```

---

## 8. Phase별 진행 현황

각 Phase 완료 시 claude.ai 채팅에서 보고 후 다음 Phase 착수

| Phase | 내용 | 상태 |
|---|---|---|
| Phase 0 | 환경 세팅, Docker, DB 스키마 | ⬜ 대기 |
| Phase 1 | Data Prep Agent, Excel 파싱 | ⬜ 대기 |
| Phase 2 | Modeling Agent, XGBoost+SHAP | ⬜ 대기 |
| Phase 3 | Execution Agent, Bayesian Opt | ⬜ 대기 |
| Phase 4 | React UI + E2E 통합 테스트 | ⬜ 대기 |
| Phase 5 | 고객사 설치 테스트 | ⬜ 대기 |
| Phase 6 | 설비 연동 + 실데이터 학습 | ⬜ 대기 |

---

## 9. 참고 파일 경로

```
개발 플랜 전체:  claude.ai 채팅에서 확인
POC 데이터:     data/raw/AI-ADES_POC_data_condition_results.xlsx
데이터 구조 설명: AI-ADES_POC_data_구성.pptx (슬라이드 3~9 참조)
DB 스키마:      data/schema/schema.sql
포트 맵:        rag-pm-matcher_PORT_MAP.md 참조 (충돌 금지)
```

---

## 10. 작업 요청 방식

Claude Code에서 작업 요청 시 아래 형식으로 주면 가장 빠릅니다.

```
[Phase N] 작업명
목표: 무엇을 만들어야 하는지
입력: 어떤 데이터/파일이 있는지
출력: 어떤 파일/결과가 나와야 하는지
제약: 특별히 주의할 것
```

**예시:**
```
[Phase 1] Excel 파서 구현
목표: Data 시트 + Sheet1 조인 → PostgreSQL 적재
입력: data/raw/AI-ADES_POC_data_condition_results.xlsx
출력: services/data-prep-agent/excel_parser.py
제약: 행 순서 1:1 조인, '300-2' 비정형 No. 처리 포함
```
