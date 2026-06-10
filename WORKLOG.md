# AI-ADES 작업 일지

## Phase 0: 환경 세팅 (2026-06-10)

### 환경 점검
- PostgreSQL: `pm-postgres` 컨테이너 (pgvector/pgvector:pg16), 기존 계정 `pmuser`/`pmpass2024`, DB `pmdb`/`openwebui` 존재. 호스트 포트 미노출(`5432/tcp` 내부 전용).
- Docker 네트워크: `pm-postgres`는 `ai-internal` 네트워크 소속 (DNS alias: `pm-postgres`, `postgres`).
- Qdrant(`6333`), Ollama(`11434`)는 호스트 포트 게시되어 있음.
- 기존 rag-pm-matcher 포트맵과 충돌 없음 확인 (`준비/rag-pm-matcher_PORT_MAP.md`).

### 작업 내용
1. **PostgreSQL 초기화**
   - `ades` role 신규 생성 (LOGIN, password: `ades`)
   - `ades_db` 데이터베이스 생성 (OWNER `ades`)
   - 접속 확인 완료 (`pm-postgres:5432`, ai-internal 네트워크 내부 전용)

2. **schema.sql 작성/적재** (`data/schema/schema.sql`)
   - `experiments`: 실험 조건 + 결과 (Excel POC 데이터 적재용)
   - `plasma_timeseries`: Plasma 센서 시계열 (Phase 6용)
   - `recipes`: Auto DOE 제안/승인 레시피

3. **.env / .env.example / .gitignore 작성**
   - `POSTGRES_HOST=pm-postgres`, `POSTGRES_DB=ades_db`, `POSTGRES_USER=ades`, `POSTGRES_PASSWORD=ades`
   - InfluxDB/MLflow/Qdrant/Ollama 등 컨테이너 DNS 이름 기준으로 작성 (ai-internal 네트워크 내부 통신 전제)
   - `EXTERNAL_NETWORK=ai-internal`

4. **docker-compose.yml 작성**
   - PostgreSQL/Qdrant/Ollama: 기존 컨테이너 그대로 사용 (신규 기동 안 함)
   - `ai-internal`을 `external: true`로 참조
   - 신규 서비스: InfluxDB(8086), MLflow(5000, sqlite 백엔드), Grafana(3010), Kafka(9092, 내부 전용)
   - **Kafka 이미지 변경**: `bitnami/kafka:3.7` 미제공 → `apache/kafka:3.7.0`(KRaft 단일노드)으로 대체. `KAFKA_HEAP_OPTS=-Xmx512m` 적용
   - data-prep/modeling/execution-agent, frontend는 `profiles: ["agents"]`로 정의 (소스 작성 후 `--profile agents up -d`)

5. **서비스 기동 확인**
   - MLflow(5000), InfluxDB(8086), Grafana(3010) HTTP 200 확인
   - Kafka 정상 기동 로그 확인 (`Kafka Server started`)
   - `ades_db`에 `experiments`/`plasma_timeseries`/`recipes` 3개 테이블 생성 확인

### 완료 기준
✅ 5개 서비스 정상 기동, 포트 충돌 없음, ades_db 스키마 적재 완료

---

## Phase 1: Data Preparation Agent (2026-06-10)

### 사전 작업
- POC Excel 구조 확인: `Data` 시트(8컬럼) + `Sheet1`(6컬럼), header는 2번째 행(`header=1`)
- Excel 파일을 `data/raw/AI-ADES_POC_data_condition_results.xlsx`로 배치
- **schema.sql 보강** (experiments 테이블 비어있어 재생성):
  - `no` → `exp_no` (UNIQUE 제약 추가, 중복 적재 방지용)
  - `final_result` → `quality`
  - `has_sensor_data` → `sensor_data_ok`
  - `is_outlier` 컬럼 신규 추가 (Thickness > 140μm 플래그)

### 구현 내용
1. **excel_parser.py** — Data 시트 + Sheet1을 행 순서 1:1 조인
   - exp_no 비정형 처리 ('300-2' 등 문자열 보존)
   - quality_score 매핑 (OK=1, 미가공=0, 과가공=-1, NG=-2)
   - sensor_data_ok ('Data 유무'=='X' → False)
   - is_outlier (Thickness > 140μm)
   - No. 결측 행 자동 제외 (328건 확보)
   - 콘솔 요약 출력: `파싱 완료: 328건 | OK:45 미가공:159 과가공:124 NG:0 센서없음:7`

2. **preprocessor.py** — PostgreSQL 적재
   - `.env` 기반 커넥션, exp_no 기준 `ON CONFLICT DO NOTHING`
   - 실제 INSERT 건수 반환

3. **influx_writer.py** — InfluxDB 적재
   - `laser_process` 버킷, measurement `experiment_result`
   - tags: exp_no, quality, m1_length, m2_length
   - fields: speed, defocus, frequency, power, kerf, depth, quality_score

4. **main.py** — FastAPI (port 8010)
   - `POST /data/upload`: 업로드 → 파싱 → PostgreSQL + InfluxDB 동시 적재
   - `GET /data/summary`: 전체 현황 (total/ok/underprocess/overprocess/ng)
   - `GET /data/distribution`: 품질별 분포 + 소재 조합별(M1/M1 length/M2/M2 length) 집계
   - `GET /health`
   - 응답 형식 `{"success", "data", "message"}` 통일

5. **Dockerfile / requirements.txt**
   - fastapi, uvicorn, pandas, openpyxl, psycopg2-binary, influxdb-client, python-dotenv, python-multipart
   - `docker-compose --profile agents build/up data-prep-agent`로 빌드 및 기동

6. **Grafana 대시보드** (`services/monitoring/grafana/dashboards/data_overview.json`)
   - InfluxDB 데이터소스 프로비저닝 추가 (`provisioning/datasources/influxdb.yml`, `provisioning/dashboards/dashboard.yml`)
   - 패널1: 품질 분포 파이 차트 (OK/미가공/과가공)
   - 패널2: Speed × Power 히트맵 (quality=OK)
   - 패널3: Defocus × Power 히트맵
   - docker-compose grafana 서비스에 provisioning 볼륨 마운트 + INFLUXDB_* 환경변수 추가

### 완료 기준 검증
1. ✅ `POST /data/upload` → PostgreSQL 328건 적재 (`미가공:159, 과가공:124, OK:45`)
2. ✅ InfluxDB `laser_process` 버킷에 `experiment_result` 328 포인트 적재 확인
3. ✅ `GET /health`, `GET /data/summary`, `GET /data/distribution` 정상 응답
4. ✅ Grafana(`http://localhost:3010`, admin/admin) 대시보드 자동 등록, 3개 패널 쿼리 모두 200 정상

### 알려진 이슈 / 후속 과제
- MLflow는 sqlite 백엔드로 단순 구동 중 → Postgres 백엔드 전환 시 `psycopg2-binary` 추가 필요 (Phase 2 검토)
- Grafana 히트맵 패널 2/3은 Influx Flux의 한계로 X축에 Speed/Defocus 값을 시간 오프셋(2020-01-01 + N초)으로 인코딩하는 방식 사용 → X축 라벨 가독성 개선 필요 (Postgres 데이터소스 기반 heatmap 검토 권장)

---

## Phase 2: Modeling Agent (2026-06-10 ~ 2026-06-11)

### 구현 내용
1. **feature_engineering.py** — `experiments` 테이블에서 학습 데이터 로드 (`sensor_data_ok=TRUE AND is_outlier=FALSE`, 319건)
   - 파생 변수 5개: `energy_density`(power/speed), `power_x_defocus`, `freq_x_power`, `thickness_ratio`(m1/m2 length), `normalized_power`(power/(speed/1000))
   - `build_feature_dataframe()` (학습용), `build_features_for_input()` (예측용 단일 입력)

2. **xgboost_pipeline.py** — kerf/depth/quality 3개 모델 학습 파이프라인
   - hold-out 20%(`random_state=42`) + 5-Fold CV, `device="cpu"`, `n_jobs=-1`(기본값)
   - quality_model: quality_score(-1/0/1, NG 0건이라 3-class)를 LabelEncoder로 인코딩, `compute_sample_weight(class_weight="balanced")`로 OK(45건) 클래스 가중치 보정, StratifiedKFold

3. **optuna_tuner.py** — 모델별 100 trials, timeout 600초, TPESampler(seed=42)
   - 탐색 공간: n_estimators 100~500, max_depth 3~8, learning_rate 0.01~0.3(log), subsample/colsample_bytree 0.6~1.0

4. **shap_analyzer.py** — TreeExplainer 기반 feature importance(정규화 합=1) + 인스턴스별 SHAP 값

5. **mlflow_tracker.py** — `ai-ades-laser-cutting` 실험에 모델별 run 기록 (params/metrics/모델 아티팩트/feature importance 그래프), `/app/models/*.pkl` 저장

6. **llm_explainer.py** — `.env LLM_PROVIDER`(ollama/claude/openai) 런타임 전환, SHAP 결과 기반 한국어 2~3문장 설명 생성

7. **main.py** — FastAPI(8011): `/model/train`, `/predict`, `/model/status`, `/health`
   - `/model/train`: FE → Optuna → XGBoost → SHAP → MLflow 전체 파이프라인 실행 + `model_metrics` 테이블에 결과 적재
   - `/predict`: kerf/depth/quality 예측 + SHAP + LLM 설명 반환

8. **Grafana 대시보드 개선** (`model_performance.json`)
   - **신규 PostgreSQL 데이터소스 추가** (`provisioning/datasources/postgres.yml`, `pm-postgres:5432/ades_db`)
   - Phase 1의 InfluxDB 히트맵 X축 인코딩 문제를 회피하기 위해 SQL 집계 + 컬러 테이블(table + color-background) 방식으로 전환
   - 패널1: Speed × Power 분포 (OK 구간, power 5W bin)
   - 패널2: Defocus × Power 분포 (전체)
   - 패널3: 모델 R²/F1 현황 (`model_metrics` 테이블 최신 행, stat 패널)
   - `model_metrics` 테이블 신규 추가 (`schema.sql`), `/model/train` 호출 시마다 1행 적재

### 주요 이슈 / 수정 사항
- **shap × numpy 2.x 호환성 문제**: `shap==0.46.0`이 `numpy>=2.0`에서 `np.floating`을 dtype으로 변환하는 코드(`_colorconv.py`)가 깨져 컨테이너 기동 실패 → `requirements.txt`에 `numpy==1.26.4` 고정으로 해결
- **Ollama 모델 불일치**: `.env`의 `OLLAMA_MODEL=qwen2.5:14b`가 실제 설치된 모델과 불일치(404) → 실제 설치된 `qwen2.5:7b-instruct`로 수정
- **Optuna 튜닝 비결정성**: `n_jobs=-1` 상태에서 `study.optimize(timeout=600)`을 사용하면, 작은 fold 데이터(약 255건)에서 스레드 생성 오버헤드로 실행시간이 매번 달라져 timeout 도달 시점(=완료된 trial 수)이 비결정적 → 재학습마다 quality_model의 `f1_ok`가 0.6 ↔ 0.526로 흔들림. **튜닝 단계 trial의 `n_jobs=1` 고정**으로 해결 (전체 학습 시간도 ~20분 → ~3분으로 단축, 결과 재현성 확보)

### 완료 기준 검증
1. ✅ `POST /model/train`: `r2_depth=0.9436`(≥0.75), `f1_ok=0.6`(≥0.60), `r2_kerf=0.9719`
   - depth_model SHAP top feature: `energy_density`(0.41), 이어서 `defocus`(0.19), `power_x_defocus`(0.16)
2. ✅ `POST /predict` (speed=500, defocus=1, frequency=200, power=15.2, m1=10, m2=25, thickness=105.0)
   - `pred_kerf=168.97`, `pred_depth=26.34`, `pred_quality="미가공"`, `confidence=0.7499`, `shap_values`/`llm_explanation` 정상 반환 (LLM: ollama/qwen2.5:7b-instruct)
3. ✅ MLflow(`http://localhost:5000`) `ai-ades-laser-cutting` 실험에 `kerf_model`/`depth_model`/`quality_model` 3개 run(FINISHED) 확인
4. ✅ 임계값 모두 충족 (재학습 후에도 `r2_depth=0.9436`, `f1_ok=0.6` 재현 확인)

### 알려진 이슈
- Grafana 대시보드 JSON의 한글 패널 제목이 API 응답을 터미널에서 확인할 때 mojibake로 표시됨 (Phase 1 `data_overview.json`에서도 동일 현상 — 파일 자체는 UTF-8 정상, 터미널/콘솔 인코딩 이슈로 추정. 브라우저에서 직접 확인 필요)

---

## 다음 단계
- Phase 3: Execution Agent (BoTorch 기반 Auto DOE, 레시피 승인 워크플로우, LLM 설명 연동)
