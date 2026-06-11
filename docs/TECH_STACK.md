# AI-ADES 기술 스택 (Tech Stack)

> 최종 갱신: 2026-06-11 (Phase 6 사전 준비 — Plasma 파서 / LSTM-Autoencoder / 자동 재학습 트리거 반영)
> 시각화 버전: [tech-stack.html](tech-stack.html)

---

## 1. 공유 인프라 (기존 rag-pm-matcher 컨테이너 재사용)

| 구성요소 | 포트 | 용도 |
|---|---|---|
| PostgreSQL | 5432 (내부) | `ades_db` 스키마 신규 추가 (pm-postgres 컨테이너 공유) |
| Qdrant | 6333 | `ades_` 접두사 컬렉션으로 분리 |
| Ollama | 11434 | LLM 추론 — `qwen2.5:7b-instruct` |

## 2. AI-ADES 전용 인프라 (docker-compose.yml)

| 구성요소 | 이미지 | 포트 | 용도 |
|---|---|---|---|
| InfluxDB | `influxdb:2.7` | 8086 | 시계열 데이터(실험 결과, Plasma 신호) 저장 |
| MLflow | `ghcr.io/mlflow/mlflow:v2.17.2` | 5000 | 모델 실험/버전 관리 (XGBoost + PyTorch) |
| Grafana | `grafana/grafana:11.3.0` | 3010 | 실시간 모니터링 대시보드 (3002 사용 금지) |
| Kafka | `apache/kafka:3.7.0` | 9092 | 내부 전용 (Phase 6 실시간 스트리밍 대비, 호스트 미노출) |

---

## 3. 백엔드 서비스별 기술 스택

### data-prep-agent (8010)

| 라이브러리 | 버전 | 용도 |
|---|---|---|
| fastapi | 0.115.6 | API 서버 |
| uvicorn[standard] | 0.32.1 | ASGI 서버 |
| pandas | 2.2.3 | Excel/CSV/ZIP 데이터 가공 |
| openpyxl | 3.1.5 | Excel 파싱 |
| psycopg2-binary | 2.9.10 | PostgreSQL 연결 |
| influxdb-client | 1.48.0 | InfluxDB 적재 |
| python-dotenv | 1.0.1 | .env 환경변수 로딩 |
| python-multipart | 0.0.20 | 파일 업로드(Excel/ZIP) 처리 |
| **requests** | **2.32.3** | 🆕 **(Phase 6)** 자동 재학습 트리거 호출용 (execution-agent 연동) |

**Phase 6 신규 모듈**
- `plasma_parser.py` — Plasma 센서 ZIP(`{exp_no}.csv`, 세미콜론 구분) → long-format DataFrame 변환
- `plasma_loader.py` — `plasma_timeseries` 테이블에 `execute_values` 벌크 적재, exp_no 매칭

### modeling-agent (8011)

| 라이브러리 | 버전 | 용도 |
|---|---|---|
| numpy | 1.26.4 | 수치 연산 |
| fastapi / uvicorn | 0.115.6 / 0.32.1 | API 서버 |
| pandas | 2.2.3 | 데이터프레임 처리 |
| psycopg2-binary | 2.9.10 | PostgreSQL 연결 |
| scikit-learn | 1.5.2 | StandardScaler, 평가지표(F1/Precision/Recall) |
| xgboost | 2.1.3 | kerf/depth/quality 3개 예측 모델 |
| shap | 0.46.0 | 모델 설명(SHAP) |
| optuna | 4.1.0 | 하이퍼파라미터 자동 튜닝 |
| mlflow | 2.17.2 | 실험 관리 |
| joblib | 1.4.2 | 모델/스케일러 직렬화 |
| matplotlib | 3.9.3 | 시각화(SHAP summary 등) |
| requests | 2.32.3 | 서비스 간 호출 |
| anthropic / openai | 0.40.0 / 1.57.0 | LLM 멀티 프로바이더 |
| **torch** | **2.5.1 (CPU 전용 wheel)** | 🆕 **(Phase 6)** LSTM-Autoencoder 학습/추론 |

> torch는 `--extra-index-url https://download.pytorch.org/whl/cpu`로 설치되는 CPU 전용 빌드입니다.
> 개발 PC(Surface Laptop Studio 1)에는 NVIDIA RTX 3050 Ti GPU가 탑재되어 있으나,
> 현재는 `GPU_ENABLED=false`로 CPU 모드 운영 중입니다.

**Phase 6 신규 모듈**
- `plasma_data.py` — `plasma_timeseries`(long) → wide-format 피벗, M1/M2/Blank 구간 분리(현재 3등분 placeholder)
- `lstm_model.py` — `LSTMAutoencoder` 정의, 슬라이딩 윈도우, 학습/복원오차/이상판정/평가 함수
- `mlflow_tracker.py`에 `log_anomaly_model_run()` 추가 (`mlflow.pytorch.log_model` — 기존 `mlflow.xgboost` 경로와 분리)

### execution-agent (8012)

| 라이브러리 | 버전 | 용도 |
|---|---|---|
| numpy | 1.26.4 | 수치 연산 |
| fastapi / uvicorn | 0.115.6 / 0.32.1 | API 서버 |
| pandas | 2.2.3 | 데이터프레임 처리 |
| psycopg2-binary | 2.9.10 | PostgreSQL 연결 |
| anthropic / openai | 0.40.0 / 1.57.0 | LLM 멀티 프로바이더 |
| gpytorch | 1.13 | Gaussian Process (Bayesian Opt 엔진) |
| botorch | 0.12.0 | Auto DOE 베이지안 최적화 |
| psutil | 6.1.0 | Admin 시스템 상태 모니터링 |

**Phase 6 변경**
- `admin.py` — `check_and_trigger_retrain()`: 누적 실험 건수 기반 경량 자동 재학습 트리거 (`AUTO_RETRAIN_THRESHOLD`, 기본 50건)
- `main.py` — `/doe/result`에서 결과 적재 후 자동 재학습 조건 점검 호출

---

## 4. 프론트엔드 (5173) — 🆕 Docker 구성 추가

| 구성요소 | 내용 |
|---|---|
| React + Vite | 운영자 UI (ExperimentPage, ApprovalPage, ResultPage, AdminPage) |
| **frontend/Dockerfile** 🆕 | `node:20-alpine` 기반, `npm install` → `npm run dev -- --host` |
| **frontend/.dockerignore** 🆕 | `node_modules`, `dist` 제외 |
| **docker-compose.yml volumes** 🆕 | `./frontend:/app` + `/app/node_modules` — 소스 변경 시 컨테이너 재빌드 없이 즉시 반영(HMR) |

> 이전에는 `docker-compose.yml`에 `build: ./frontend`만 정의되어 있고 `Dockerfile`이 없어
> 실제로는 빌드가 불가능한 상태였습니다. 이번에 Dockerfile/.dockerignore를 추가하고
> 볼륨 마운트로 개발 핫리로드를 지원하도록 구성을 완성했습니다.

---

## 5. 개발/운영 환경

| 항목 | 내용 |
|---|---|
| 개발 장비 | MS Surface Laptop Studio 1 (RAM 32GB, **NVIDIA GeForce RTX 3050 Ti Laptop GPU 탑재**) |
| GPU_ENABLED | `false` (개발 단계, CPU 모드) — 고객사 설치 시 `true`로 전환 예정 |
| 컨테이너 소스 마운트 | data-prep-agent / modeling-agent / execution-agent: ❌ (이미지 빌드 필요) · frontend: ✅ (볼륨 마운트, 핫리로드) |

---

## 6. Phase 6 변경 요약

| 영역 | 변경 전 | 변경 후 |
|---|---|---|
| 개발 PC GPU 사양 | "GPU 없음"으로 잘못 기재 | RTX 3050 Ti 탑재 확인, 문서 정정 |
| Plasma 센서 데이터 | 적재 경로 없음 | ZIP 업로드 → `plasma_timeseries` 적재 (`plasma_parser.py`, `plasma_loader.py`) |
| 이상감지 모델 | 없음 | LSTM-Autoencoder 골격 추가 (`lstm_model.py`, `plasma_data.py`, torch 2.5.1) |
| 모델 재학습 | 수동 트리거만 존재 | 누적 실험 건수 기반 경량 자동 재학습 트리거 추가 |
| frontend Docker화 | `build: ./frontend`만 정의(빌드 불가) | Dockerfile/.dockerignore/볼륨 마운트 추가로 정상 빌드·핫리로드 |
| `model_metrics` 스키마 | `n_experiments` 컬럼 없음 | `n_experiments` 컬럼 추가 (자동 재학습 비교 기준) |

---

## 참고 문서

- 전체 디렉토리 구조 / LLM 멀티 프로바이더: [ARCHITECTURE.md](ARCHITECTURE.md)
- Phase 6 작업 상세 설명(쉬운 버전): [phase6-guide.html](phase6-guide.html)
- 작업 일지: [WORKLOG.md](../WORKLOG.md)
