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

## 형상관리 / 문서화 (2026-06-11)

### 작업 내용
1. **Git 저장소 초기화** — `D:\claude\ai-ades`에 `git init`, `.gitignore` 보강
   - `services/*/models/*` (학습된 .pkl 모델 산출물) 제외 (`.gitkeep`만 추적)
   - `.claude/` (내부 파일), `준비/AI-ADES POC data 구성.pptx`(85MB) 제외
2. **GitHub 원격 저장소 연결 및 최초 푸시**
   - `https://github.com/twowings-hub/ai-ades` 를 `origin`으로 등록, `main` 브랜치 푸시 (commit `53ee5f8`)
   - Phase 0~2 전체 소스/스키마/대시보드/문서 31개 파일 포함
3. **CLAUDE.md 갱신** (commit `5fbf0cb`)
   - Phase 0/1/2 상태를 ✅ 완료로 변경, Phase 4에 "Admin Console" 범위 추가
   - `OLLAMA_MODEL`을 실제 설치 모델인 `qwen2.5:7b-instruct`로 동기화 (기술스택 표 + 환경변수 예시 2곳)
   - 신규 11장 "Phase 4 추가 사양 — Admin Console (예정)" 추가
     - 작업 1: 관리자 API 엔드포인트 전체 목록 (시스템 상태/LLM 관리/모델 재학습/설정 관리/사용자 관리/알림/감사로그/서비스 관리/데이터 관리)
     - 작업 2: 신규 DB 테이블(`users`, `notification_settings` 등) — 사용자 입력이 중간에 끊겨 일부 컬럼/`audit_logs` 등 테이블 정의 누락, 착수 시 재확인 필요로 명시
     - 작업 3: `frontend/src/pages/AdminPage.jsx` 개요
     - **전제조건 명시**: Phase 3(Execution Agent 기본 구조)이 먼저 완료되어야 착수 가능

### 다음 단계
- Phase 3: Execution Agent (BoTorch 기반 Auto DOE, 레시피 승인 워크플로우, LLM 설명 연동) — 다음 세션에서 작업지시서 수령 후 착수
- Phase 4 Admin Console: Phase 3 완료 후 착수, 누락된 DB 테이블 스펙 재확인 필요

---

## 소재 종류 관리 + ExperimentPage 외삽 경고 + Admin LLM 버그 수정 (2026-06-11)

> Phase 3(Execution Agent), Phase 4(Admin Console 9개 섹션)는 본 세션 이전에 이미 구현된 상태에서 시작.
> CLAUDE.md의 Phase 0~2 표기를 실제 진행 상황에 맞춰 Phase 3 ✅ 완료, Phase 4 진행중으로 갱신 (자세한 내용은 CLAUDE.md/docs/PHASE4_ADMIN_SPEC.md 참고).

### 1. 소재 종류(material_types) 관리 — Admin CRUD + 실험 페이지 연동
- `data/schema/schema.sql`: `material_types` 테이블 신규 (`category`('m1'/'m2'), `name`, `description`, `is_active`), Glass/Film 시드 적재
- `services/execution-agent/material_types.py` 신규: `GET/POST/PATCH/DELETE /admin/material-types` (전체 audit_logs 기록)
- `services/execution-agent/main.py`: `GET /material-types`(공개, 활성 항목만) 추가, `material_types.router` 등록
- `services/execution-agent/recipe_db.py`: `m1_glass`/`m2_film` 컬럼 추가, `find_recipe`/`save_recipe`가 소재 종류까지 매칭
- `frontend/src/pages/admin/MaterialTypesSection.jsx` 신규: 추가/수정/활성·비활성/삭제 전체 CRUD UI
- `frontend/src/pages/AdminPage.jsx`: "소재 종류 관리" 섹션 추가

### 2. ExperimentPage — M1/M2 길이·두께 자유 입력 + 외삽(extrapolation) 경고
- 사용자 질의: "M1, M2 값이 고정되어 있는데 전혀 다른 소재/두께가 투입되는 경우는?"
- 결론: M1/M2 길이·두께를 고정 버튼 → 자유 숫자 입력 + 프리셋 버튼으로 전환, 학습 데이터 범위를 벗어나면 경고 표시
- `services/data-prep-agent/main.py`: `/data/distribution`에 `data_ranges`(m1_length_mm/m2_length_mm/thickness_um의 min/max) 추가
  - 현재 범위: m1_length∈[4,20]mm, m2_length∈[10,50]mm, thickness∈[98,177.5]μm
- `frontend/src/pages/ExperimentPage.jsx`: M1/M2 Length, Thickness를 숫자 입력 필드로 변경, `outOfRange()` 헬퍼로 범위 이탈 시
  "⚠ 학습 데이터 범위를 벗어났습니다. 예측 신뢰도가 낮을 수 있습니다 (Auto DOE 탐색 횟수 증가 권장)" 경고 표시
- `frontend/src/context/SessionContext.jsx`: `material` 상태에 `m1_glass`/`m2_film` 추가

### 3. 업로드 테스트용 샘플 Excel 10개 생성
- `data/test/generate_test_files.py` 신규: POC Data+Sheet1 형식(header=1)으로 10건씩 들어있는 Excel 10개 생성
- `data/test/AI-ADES_test_upload_sample_01~10.xlsx` (No.2001~2100, 기존 데이터와 No. 중복 없음)
- `excel_parser.parse_excel()`로 01번 파일 파싱 검증 완료 (10건, OK:5/미가공:3/NG:2/센서없음:1, is_outlier 정상 플래그)

### 4. 버그 수정 — Admin "LLM 모델 선택"에서 provider별 모델 목록 미분리
- 증상: provider를 `openai`로 선택해도 모델 드롭다운에 `claude-sonnet-4-6`이 함께 노출됨
- 원인: `admin.py`의 `API_MODELS`가 `["claude-sonnet-4-6","gpt-4o","gpt-4o-mini"]` 단일 배열로, provider 구분 없이 그대로 응답
- 수정:
  - `services/execution-agent/admin.py`: `API_MODELS = {"claude": [...], "openai": [...]}` 딕셔너리로 변경, `/admin/llm/available-models` 응답의 `api` 필드를 provider별 딕셔너리로 변경
  - `frontend/src/pages/admin/LlmSection.jsx`: `currentOptions = provider === 'ollama' ? models.ollama : (models.api?.[provider] ?? [])`로 수정
- **컨테이너 재빌드 필요했음**: `execution-agent`는 소스 볼륨 마운트가 없어 `restart`만으로는 코드 변경이 반영되지 않음
  → `docker compose --profile agents build execution-agent && docker compose --profile agents up -d execution-agent` 후 정상 응답 확인
  (`docs/OPERATIONS.md`에 이 주의사항 명시)

### 5. 문서 정리
- `CLAUDE.md`가 517줄로 비대해져 세션 시작 시 토큰 부담 → 핵심(프로젝트 개요/판정기준·탐색공간/코딩규칙/Phase 현황/작업요청방식)만 남기고 분리
- 신규: `docs/ARCHITECTURE.md`(디렉토리 구조·기술스택), `docs/DATA_SPEC.md`(Excel 구조·소재종류·외삽 경고), `docs/OPERATIONS.md`(실행명령·환경변수·재빌드 주의사항), `docs/PHASE4_ADMIN_SPEC.md`(Admin Console 설계+구현현황)

### 다음 단계
- Phase 4 E2E 통합테스트: `/admin` 9~10개 섹션 브라우저 실동작 확인, ExperimentPage→ApprovalPage→ResultPage 전체 플로우, 신규 샘플 Excel 업로드 테스트
- 미해결 메모: `material_types`에 중복 등록된 "sample"(id=4 m1, id=5 m2) 항목 정리 여부 확인 필요

---

## CLAUDE.md GPU 정정 + Phase 6 사전 준비 3종 (2026-06-11)

> 고객사 사전 미팅 전, Phase 6("설비 연동 + 실데이터 학습") 항목 중 고객사 협의 없이 개발 가능한 항목을 우선 진행.
> 4번째 항목(설비 통신 드라이버 추상화)은 OPC-UA/RS-232/Ethernet 등 프로토콜·파라미터·Plasma 파일 규격이 고객사 확인 전까지 미정이므로 보류 결정.

### 0. 문서 정정 — 개발 장비 GPU 사양 (commit `415e545`)
- `docs/AI-ADES_개발플랜.md`: Surface Laptop Studio 1(32GB)에 NVIDIA GeForce RTX 3050 Ti Laptop GPU가 실제로 탑재되어 있음을 반영
  - 5행: "GPU 없음" → "NVIDIA GeForce RTX 3050 Ti Laptop GPU 탑재"
  - 622행: `GPU_ENABLED=false` 주석에 "Surface: GPU(RTX 3050 Ti) 탑재되어 있으나 개발 단계는 false" 명시

### 1. Plasma ZIP 파서 (Phase 6 사전 준비 ①)
- `services/data-prep-agent/plasma_parser.py` 신규: ZIP 내 `{exp_no}.csv`(세미콜론 구분, `Index;Time;Area;Plasma;P-Raw;Temp;T-Raw;Refl;R-Raw`)를 파싱
  - `PLASMA_CHANNELS = ["Area","Plasma","P-Raw","Temp","T-Raw","Refl","R-Raw"]`
  - `parse_plasma_zip(file_path)` → long-format DataFrame(exp_no, elapsed_ms, channel, value), `Time`(초)을 `*1000`하여 `elapsed_ms`로 변환
- `services/data-prep-agent/plasma_loader.py` 신규: `load_plasma_to_postgres(df)` → `plasma_timeseries` 테이블에 `execute_values` 벌크 적재
  - `experiments.exp_no`로 매칭해 `experiment_id` 결정, 미매칭 exp_no는 건너뛰고 결과에 보고
  - `ts`는 `pd.Timestamp.now(tz="UTC")` 기준 + `elapsed_ms`로 임시 계산 (실데이터의 실제 타임스탬프 규격은 고객사 확인 필요)
- `services/data-prep-agent/main.py`: `POST /data/plasma/upload` 엔드포인트 추가 (.zip 검증 → 파싱 → 적재 → 결과 메시지)
- `data/test/generate_plasma_test_zip.py` 신규: exp_no 1~5, 500포인트 sin파+노이즈 합성 데이터로 테스트 ZIP 생성
- 검증: 합성 ZIP 업로드 → 5개 실험 매칭, 정상 적재 확인 후 테스트 데이터 삭제(`DELETE FROM plasma_timeseries`)
- **확인 필요(고객사)**: ZIP 내 CSV 파일명=exp_no 가정, `Time` 컬럼 단위(초) 가정, 실제 타임스탬프 산출 방식

### 2. LSTM-Autoencoder 골격 (Phase 6 사전 준비 ②)
- `services/modeling-agent/plasma_data.py` 신규
  - `list_experiment_ids()`: `plasma_timeseries`에 데이터가 있는 experiment_id 목록
  - `load_plasma_wide(experiment_id)`: long→wide 피벗(`PLASMA_CHANNELS` 순서로 정렬, `ffill().bfill()`)
  - `split_segments(df)`: M1/M2/Blank 3구간으로 분리 — **현재는 행 수 균등 3분할 placeholder**, 실제 구간 검출(change-point detection) 로직으로 교체 필요
- `services/modeling-agent/lstm_model.py` 신규
  - `LSTMAutoencoder`(encoder LSTM → latent → decoder LSTM → Linear), `WINDOW_SIZE=50, STRIDE=10, HIDDEN_SIZE=16`
  - `make_windows`, `train_autoencoder`(StandardScaler + MSE/Adam, threshold=재구성오차 95퍼센타일), `compute_reconstruction_error`, `detect_anomalies`, `evaluate_anomaly_detection`(F1/Precision/Recall)
- `services/modeling-agent/requirements.txt`: CPU 전용 `torch==2.5.1` 추가 (`--extra-index-url https://download.pytorch.org/whl/cpu`)
- `services/modeling-agent/mlflow_tracker.py`: `log_anomaly_model_run()` 신규 (`mlflow.pytorch.log_model` 사용 — 기존 `log_model_run`은 `mlflow.xgboost` 전용이라 PyTorch 모델에 사용 불가)
- `services/modeling-agent/main.py`
  - `POST /model/train-anomaly`: 전체 실험의 wide plasma 데이터를 윈도우화해 LSTM-Autoencoder 학습, 모델/스케일러/threshold를 `models/`에 저장 + MLflow 기록
  - `POST /predict-anomaly` (`{"experiment_id": int}`): 구간별(M1/M2/Blank) 재구성오차·이상비율 반환
  - `GET /model/anomaly-status`: 학습된 이상감지 모델의 threshold/final_loss/n_windows 조회
- 검증: torch 포함 이미지 재빌드(`docker compose --profile agents build modeling-agent`) 후 합성 데이터로 학습→예측 엔드투엔드 정상 동작 확인
- **확인 필요(고객사)**: `split_segments`의 실제 M1/M2/Blank 구간 판별 기준, `WINDOW_SIZE`/`HIDDEN_SIZE` 등 하이퍼파라미터는 실데이터로 재튜닝 필요

### 3. 경량 자동 재학습 트리거 (Phase 6 사전 준비 ③)
- 사용자 결정: Surface 32GB 메모리 부담을 고려해 신규 Airflow 컨테이너 없이 "경량 트리거(권장)" 방식 채택
- `data/schema/schema.sql` + 운영 DB: `model_metrics`에 `n_experiments INTEGER` 컬럼 추가 (`ALTER TABLE`로 즉시 반영)
- `services/execution-agent/admin.py`
  - `AUTO_RETRAIN_THRESHOLD`(.env, 기본 50) 추가
  - `check_and_trigger_retrain()`: 현재 `experiments` 건수 - 마지막 학습 시점 `n_experiments` 차이가 임계값 이상이고 재학습이 진행 중이 아니면 백그라운드 재학습 스레드 실행 + `audit_logs`에 `action_type="retrain", operator="system(auto)"`로 기록
  - `POST /admin/model/check-auto-retrain` 엔드포인트 추가
- `services/modeling-agent/main.py`: `_save_metrics_to_db()`에 `n_experiments` 파라미터 추가, 학습 시 `len(df)`로 기록
- `services/data-prep-agent/main.py`: `EXECUTION_AGENT_URL` 추가, `/data/upload` 적재 성공 시 `_check_auto_retrain()` 호출(실패해도 업로드에 영향 없음)
- `services/execution-agent/main.py`: `/doe/result`에서 실험 결과 적재 후 `admin.check_and_trigger_retrain()` 호출
- `.env`/`.env.example`: `EXECUTION_AGENT_URL`, `AUTO_RETRAIN_THRESHOLD=50` 추가
- 검증: 실제 운영 DB(experiments 338건)로 트리거 호출 → 임계값 초과로 실제 XGBoost 재학습 실행됨(depth R²=0.83, quality F1_OK=0.72), `model_metrics` id=6에 `n_experiments=328` 기록 확인 (테스트가 아닌 실제 모델 갱신)

### 다음 단계
- Phase 6 4번째 항목(설비 통신 드라이버 추상화: OPC-UA/RS-232/Ethernet 등)은 고객사 사전 미팅에서 프로토콜·파라미터 노출 범위·Kerf/Depth 측정 가능 여부·Plasma 파일 규격 확인 후 착수
- Plasma 관련 placeholder(타임스탬프 계산, 파일명=exp_no 가정, split_segments 3분할) 실데이터 확인 후 정정
- 본 세션 변경사항(Phase 6 사전 준비 3종)은 아직 git commit 미완료

---

## 결과 보고 UX 개선 + Plasma 파서 완성 + 실험 이력 조회 (2026-06-12)

### 1. 결과 보고 화면 — 실험 결과 설명란(notes) 추가
- `data/schema/schema.sql` / `experiments` 테이블: `notes` 컬럼 추가
- `services/execution-agent/recipe_db.py`: `save_recipe()`에 `notes` 파라미터 추가, 레시피 저장/조회 시 `notes` 포함
- `services/execution-agent/main.py`: `DoeResultRequest`/`_insert_experiment`에 `notes` 추가
- `frontend/src/pages/ResultPage.jsx`: 실험 결과 설명(보고용) 입력란(textarea) 추가, 저장 시 함께 전송

### 2. Plasma CSV 파서 완성 (수정판, Phase 6-1)
- `services/data-prep-agent/plasma_parser.py` 전면 재작성
  - 콤마/세미콜론 이중 구분자 형식(메타데이터: `:`, 시계열: `;`, 헤더 `Index;Time...`) 파싱
  - `detect_region()`: Time 임계값 + Plasma 신호 검증으로 M1/M2/Blank 구간 자동 분류, M1/M2 미측정·time_shifted 플래그 산출
  - `downsample()`: `PLASMA_DOWNSAMPLE_FACTOR`(기본 100) 단위 행 스트라이드 다운샘플링
  - `parse_plasma_zip()`: ZIP 내 CSV 전체를 파싱해 `{exp_no, meta, df, flags, warnings}` 리스트 반환
- `services/data-prep-agent/plasma_loader.py` 전면 재작성
  - `plasma_timeseries`에 `region` 컬럼 추가 반영, `plasma_measurements`(측정 메타: configuration/result/comment/duration/sample_rate 등) 테이블 신규
  - `load_to_db()`: exp_no→experiment_id 매칭 후 시계열 batch insert + 측정 메타 insert
  - `get_plasma_summary()`: 전체 파일 수, 미매칭 exp_no, M1/M2 미측정·time_shifted 건수, 총 샘플 수 집계
- `services/data-prep-agent/main.py`: `POST /data/upload-plasma`(zip 업로드→파싱→적재, 결과/경고 집계), `GET /data/plasma-summary` 신규
- `data/schema/schema.sql`: `plasma_timeseries.region` 컬럼, `plasma_measurements` 테이블 + 인덱스 추가
- `.env`/`.env.example`: `PLASMA_M1_END_S`, `PLASMA_M2_END_S`, `PLASMA_EXPECTED_DURATION_S`, `PLASMA_TIME_TOLERANCE_S`, `PLASMA_DETECT_THRESHOLD`, `PLASMA_DOWNSAMPLE_FACTOR` 추가
- `data/test/generate_plasma_test_zip.py` 재작성: 25,000행(250kHz, 0.1s) 5개 테스트 케이스(정상/M1 미측정/M1+M2 미측정/time_shifted/메타 누락)
- 검증: 재생성한 테스트 ZIP 업로드 → 경고/카운트 정상 (m1_not_measured=2, m2_not_measured=1, time_shifted=1, total_samples=7875)

### 3. AI 평가 자동 입력 (결과 설명란 초안 생성)
- `services/execution-agent/llm_explainer.py`
  - `RESULT_PROMPT_TEMPLATE` 추가 (예측값 vs 실측값 비교 + 판정 결과를 2~3문장 보고용 메모로 작성)
  - 공통 `_call_llm()` 디스패처로 ollama/claude/openai 호출 통합, `generate_explanation`/`generate_result_evaluation` 모두 사용
- `services/execution-agent/main.py`: `POST /doe/evaluate` 신규 — 실측 Kerf/Depth와 예측값을 비교해 AI 평가 메모 초안 생성
- `frontend/src/pages/ResultPage.jsx`
  - Kerf/Depth 입력 완료(blur) 시 설명란이 비어있으면 AI 평가를 자동 생성, "AI 평가로 채우기" 버튼으로 수동 재생성도 가능
  - 생성된 초안은 운영자가 자유롭게 수정/보완 가능

### 4. AI 평가 생성 진행 상황 표시
- `frontend/src/index.css`: `.progress-bar`/`.progress-bar-fill` 추가 (width 기반, `transition: width 0.3s linear`)
- `frontend/src/pages/ResultPage.jsx`: 경과 시간(`evalElapsedMs`, 200ms 간격) 대비 예상 소요시간(8초) 기준으로 진행률(%)·예상 남은 시간을 점진적으로 표시
  - (1차 시도: CSS sweep 애니메이션 → "너무 빨리 움직여 정신없다"는 피드백으로 점진적 진행률 표시로 변경)

### 5. 실험 이력 조회 페이지 신규
- `services/execution-agent/main.py`: `GET /experiments` 신규 — `quality`(판정)/`search`(실험번호·설명 ILIKE)/`limit`/`offset` 필터·페이지네이션 지원, `notes` 포함 전체 컬럼 반환
- `frontend/src/pages/ExperimentHistoryPage.jsx` 신규
  - 판정 필터(전체/OK/미가공/과가공/NG) + 실험번호/설명 검색 + 페이지네이션
  - 각 실험을 카드로 표시: 좌측에 **입력값(M1/M2/Thickness) / 가공 조건(Speed·Defocus·Frequency·Power) / 측정 결과(Kerf·Depth)** 3개 컬럼 그룹, 우측에 설명(보고용)란을 최대한 넓게 배치
- `frontend/src/App.jsx`, `frontend/src/components/Layout.jsx`: `/history` 라우트 및 "실험 이력" 메뉴 추가
- 검증: execution-agent 재빌드 후 `/experiments` 필터(quality/search) 정상 동작 확인 (전체 341건)

### 6. AI 제안 승인 화면 — 결과 해석 가이드 분리
- `frontend/src/pages/ApprovalPage.jsx`: "결과 해석 가이드"는 일반 설명으로 유지하고, **이번 제안의 SHAP 해석("이번 제안 해석")**은 진한 배경의 별도 박스로 분리 표시

### 다음 단계
- 본 세션 변경사항 및 직전 세션의 Phase 6 사전 준비 3종 모두 git commit 미완료 (services/, frontend/, data/schema/, .env.example 등 다수 변경)
- Phase 4 E2E 통합테스트 잔여
- Plasma 실데이터 확인 후 region 판별 임계값(M1_END_S/M2_END_S/DETECT_THRESHOLD) 재조정 필요

---

## AI 채팅 — 이력 관리(좌측 사이드바) + 영어 용어 표기 개선 (2026-06-12)

### 1. AI 채팅 이력(세션) 관리
- `data/schema/schema.sql`: `chat_sessions`(세션, 제목/생성·수정시각), `chat_messages`(세션별 user/assistant 메시지, provider) 테이블 신규 + 인덱스 추가, `ades_db`에 직접 적용
- `services/execution-agent/chat_history.py` 신규: 세션 생성(`create_session`, 첫 질문으로 제목 생성)/조회(`list_sessions`, `get_messages`)/갱신(`touch_session`)/삭제(`delete_session`)
- `services/execution-agent/chat_routes.py` 신규(APIRouter): `POST /chat`(세션 단위 이력 저장), `GET /chat/sessions`, `GET /chat/sessions/{id}`, `DELETE /chat/sessions/{id}`
- `services/execution-agent/main.py`: 기존 `/chat*` 엔드포인트 제거 후 `chat_routes` 라우터로 이전 (627줄 → 577줄, 500줄 제한에는 여전히 초과 — 추후 추가 분리 필요)
- `frontend/src/pages/ChatPage.jsx`: 좌측에 채팅 이력 목록(claude.ai 스타일) 추가
  - "+ 새 채팅" 버튼으로 새 세션 시작
  - 이력 클릭 시 해당 세션의 대화 불러오기, × 버튼으로 삭제
  - `handleSend`를 신규 API 계약(`{session_id, message, provider}` → `{session_id, reply}`)에 맞게 재작성
- 검증: execution-agent 재빌드 후 세션 생성/이어가기(대화 맥락 유지)/조회/삭제 curl 테스트 모두 정상

### 2. AI 채팅 — 영어 용어(M1/M2, Speed 등) 표기 개선
- `services/execution-agent/chat.py`의 `CHAT_SYSTEM_TEMPLATE` 답변 규칙 수정: 문장은 한국어로 작성하되 M1/M2, Speed/Defocus/Frequency/Power, Depth/Kerf, OK 등 소재·파라미터·판정 명칭은 영어 표기 그대로 사용(예: "엠원" 대신 "M1"), 한자/중국어는 계속 금지
- 검증: execution-agent 재빌드 후 Claude 응답에서 Glass/Film/Speed/Defocus/Frequency/Power/Depth/Kerf/OK가 영어 표기로 정상 출력됨을 확인

### 3. 참고 (Q&A, 코드 변경 없음)
- 채팅 이력 저장 위치: PostgreSQL `ades_db`(`chat_sessions`/`chat_messages`), `pm-postgres` 컨테이너의 Docker 볼륨(`rag-pm-matcher_pm_postgres_data`)에 영구 저장 — 재부팅/컨테이너 재시작에도 유지, 볼륨 삭제 시에만 소실
- 관리자 LLM 선택(`/admin/llm/switch`, `_STATE["provider"]`)과 채팅창 LLM 선택(요청별 `provider`, 기본값 `CHAT_LLM_PROVIDER`)은 서로 완전히 독립적으로 동작

### 4. 브라우저 탭 제목 변경
- `frontend/index.html`: `<title>`을 "frontend" → "AI-ADES"로 변경

### 다음 단계
- 본 세션 변경사항도 git commit 미완료 (이전 세션 변경사항 포함 다수 누적)
- main.py 500줄 제한 초과(577줄) 추가 분리 검토

---

## Phase 4 E2E 통합테스트 + main.py 분리 + 운영 가이드 보강 (2026-06-12)

### 1. Phase 4 E2E 통합테스트 (API 레벨)
- 브라우저 자동화 도구 부재로 GUI 스크린샷은 생략, 각 화면이 호출하는 API를 실제로 호출해 검증
- `/admin` 10개 섹션(상태/서비스/LLM/재학습/판정기준/소재종류/사용자/알림/감사로그/데이터)의 조회 API 전부 정상
- Auto DOE 풀플로우: `/doe/suggest` → `/doe/explanation`(LLM 비동기 생성) → `/doe/approve` → `/doe/evaluate`(AI 평가) → `/doe/result`(레시피 저장) 정상 동작 확인, 테스트 데이터는 검증 후 정리(원상복구: experiments 343/recipes 10/audit_logs 39)
- `/data/upload`(샘플 Excel 01) → 10건 적재 확인 후 정리
- `/experiments` 필터(quality)/검색(exp_no, notes) 정상
- `/chat` 세션 생성/목록/조회/삭제 정상 (한글 제목 DB 저장은 정상, 표시 문제는 Git Bash↔Python 파이프의 콘솔 인코딩 이슈였음 — 앱 버그 아님)
- 이전 세션의 `material_types` 중복 "sample" 항목은 이미 정리되어 있음을 확인

### 2. frontend EIO 크래시 — 운영 가이드 추가
- `docker logs ades-frontend`에서 직전 세션(06-12 05:51) `vite.config.js` 변경 시 watcher 재시작 도중 `Error: EIO: i/o error, stat '/app'`로 Node 프로세스 크래시 → `restart: unless-stopped`로 결국 복구되었으나 호스트 절전 등으로 장시간(3시간 40분) 다운됨
- `docs/OPERATIONS.md`: frontend가 호스트 Vite가 아니라 `ades-frontend` 컨테이너(바인드마운트+HMR)로 동작함을 정정, `vite.config.js` 수정 후 `docker compose restart frontend` 수동 실행 권고 추가

### 3. main.py 분리 (CLAUDE.md 500줄 제한 대응)
- `services/execution-agent/main.py`(577줄)에서 Auto DOE 워크플로우 전체를 `doe_routes.py`(신규, APIRouter prefix="/doe")로 이동
  - 이동 대상: `/doe/suggest`, `/doe/explanation/{id}`, `/doe/approve`, `/doe/reject`, `/doe/evaluate`, `/doe/result`와 관련 Pydantic 모델, `SUGGESTIONS` 전역 상태, `_call_predict`/`_generate_explanation_bg`/`_get_suggestion`/`_insert_experiment` 헬퍼
  - `_response`는 기존 다른 라우터들과 동일하게 `responses.make_response`를 사용하도록 통일
- main.py는 195줄로 축소, `/health`/`/material-types`/`/recipes`/`/experiments`/`/recipes/{m1_length}/{m2_length}`만 남음 (doe_routes.py는 400줄)
- execution-agent 재빌드 후 `/doe/suggest`→`/doe/approve`→`/doe/evaluate` 재검증 및 `/admin/health`, `/material-types`, `/experiments` 정상 응답 확인 (DB 카운트 원복 확인)

### 다음 단계
- 본 세션 변경사항(E2E 테스트, OPERATIONS.md, doe_routes.py 분리) git commit 미완료
- Plasma 실데이터 확인 후 region 판별 임계값 재조정 필요 (보류 중)

---

## 테스트 데이터 정리 기능 + 자동 재학습 진행도 + 관리자/운영 화면 UI 정리 (2026-06-13)

### 1. 테스트 데이터 정리 기능 (Auto DOE 인위 데이터 안전 삭제)
- 배경: 시나리오 테스트로 생성된 미가공/과가공 Auto DOE 실험이 재학습 임계값(50건)에 누적되어 모델을 오염시킬 우려 → 재학습 반영 전에 안전하게 정리하는 관리자 기능 신설
- `services/execution-agent/admin_data.py`:
  - `GET /admin/data/test-experiments` — `exp_no LIKE 'DOE-%'` 이면서 **마지막 학습 시각 이후 생성된**(아직 미반영) 실험만 조회
  - `POST /admin/data/test-experiments/delete` — 2중 안전장치: (1) `exp_no`가 `DOE-`로 시작하지 않는 원본 업로드 데이터 제외, (2) 이미 재학습에 반영된(created_at ≤ 마지막 학습 시각) 데이터 제외. 삭제 시 `approval.log_audit(action_type="data_cleanup")` 감사로그 기록
- `frontend/src/pages/admin/DataManagementSection.jsx`: "테스트 데이터 정리" 카드 추가 — 체크박스 목록(스크롤·sticky 헤더), "선택 삭제(N건)" 버튼, **"삭제" 타이핑 확인 모달**(오삭제 방지)
- 검증: curl로 빈 선택→400, 존재하지 않는 id→400("삭제 가능한 항목 없음"), 정상 삭제 후 `audit_logs`에 `data_cleanup` 기록 확인

### 2. 자동 재학습 진행도 표시
- `services/execution-agent/admin.py`: `_get_retrain_progress()` 헬퍼 추출(조회 전용, 트리거 안 함) + `GET /admin/model/auto-retrain-progress` 신규. `check_and_trigger_retrain()`이 이 헬퍼를 재사용하도록 중복 제거
  - 반환: `current_count`, `last_trained_count`, `added_since_last_training`, `threshold`, `remaining`
- `frontend/src/pages/admin/RetrainSection.jsx`: "자동 재학습 진행도" 카드(progress bar) 추가 — 누적 N/50건, 남은 건수 안내, 재학습 완료(running→idle) 시 자동 재조회
- 검증: `GET /admin/model/auto-retrain-progress` 정상 응답 확인

### 3. 관리자 콘솔 UI 정리
- `frontend/src/index.css` `.admin-table` 행 높이/폰트 반복 조정 → 최종 `td padding 2px 10px / font-size 14px / line-height 1`, 제목행은 별도 여유(`th padding 6px 10px`), `.btn-sm`·`.pill` line-height 보정. `.btn`에 `white-space: nowrap` 추가(버튼 줄바꿈 방지)
- `frontend/src/pages/admin/MaterialTypesSection.jsx`: 소재 종류 목록을 `.admin-table`로 전환, 셀 높이 축소, 10건 이상이면 `maxHeight`+sticky 헤더로 스크롤
- `frontend/src/pages/admin/DataManagementSection.jsx`: "테이블 현황" 표를 `.admin-table`로 통일(건수 우측정렬), 카드 간 여백 축소
- `frontend/src/pages/admin/LlmSection.jsx`: "현재 적용 모델"과 "프로바이더/모델 전환" 카드 통합, 기본 select 값을 현재 적용값으로 맞춤, 프로바이더·모델 선택부를 진한 배경 박스로 묶고 전환/연결 테스트 버튼도 박스 내 포함

### 4. Claude Code CLI 모델 변경
- 작업용 Claude Code CLI 모델을 Sonnet 4.6 → **Opus 4.8**로 전환(`/model opus`, 기본값 저장). ※ 앱 내 LLM 프로바이더 설정과는 무관(별개)

### 5. 시스템 상태 화면 정리 (`SystemStatusSection.jsx`)
- 두 카드 패딩 축소(`12px 16px`), 카드 간 여백 축소
- "리소스 사용량"과 "최근 모델 학습 지표" 표를 flex로 좌우 배치 → 이후 위치 교체(**왼쪽: 학습 지표 / 오른쪽: 리소스 사용량**)
- 학습 시각을 `formatShortDateTime()`로 `YYYY-MM-DD HH:mm` 단축 표시(초·마이크로초·타임존 생략)

### 6. 레시피 조회 화면 정리 (`RecipeSearchPage.jsx`)
- 입력 카드 하단 패딩·"전체 레시피 목록" 카드 상단 패딩·카드 간 여백 축소
- "레시피 조회" 버튼 직후 나오는 결과 카드(녹색 "N건 찾았습니다" 박스)·단일 레시피 카드·에러/없음 배너의 `marginTop` 16 → 4로 축소

### 7. 상단 네비게이션 메뉴 버튼 강조 (`Layout.jsx`)
- 비활성 메뉴에 옅은 배경(`#eceef1`) + 진한 테두리(`#9aa0a8`) 적용해 7개 메뉴가 버튼처럼 또렷하게 보이도록 개선(활성 메뉴는 기존 accent 유지)

### 8. 결과 보고 화면 — 승인된 파라미터 테이블 (`ResultPage.jsx`)
- `.table-bordered` 클래스 신규(`index.css`, 셀마다 `border 1px solid #9aa0a8`) 적용해 진한 격자 테두리
- Speed/Defocus/Frequency/Power 및 예측값 컬럼 가운데 정렬 + 단위 표기 추가(`PARAM_UNITS`: Speed mm/s, Defocus mm, Frequency kHz, Power W)

### 검증 방식
- 프론트엔드 변경은 헤드리스 Chrome(`--headless --screenshot`)로 실제 렌더링 캡처해 확인(`/recipes` 여백, 네비 버튼 테두리 등). 결과 보고 표는 승인된 제안이 있어야 표시되어 직접 캡처는 생략

### 다음 단계
- 본 세션 변경사항 git commit 미완료(이전 세션 누적분 포함)

---

## 운영 플로우 UX 수정 + 결과 저장 확인절차/사전 판정 + Phase5·6 미팅 문서 + E2E 검증 (2026-06-13, 2차 세션)

### 1. 검증된 레시피("1회 확인 실험") Auto DOE 시작 버튼 미동작 수정
- 증상: 소재 조합에 검증된 레시피(Thickness 일치)가 있을 때 "Auto DOE 시작"을 눌러도 승인 화면으로 넘어가지 않음
- 원인: `ExperimentPage.jsx` `runSuggest`에서 `recipe_found=true`면 `navigate('/approval')` 대신 눈에 안 띄는 중간 배너(`recipeBanner`)만 표시 → 한 번 더 클릭해야 진행
- 수정: 레시피 보유/신규 조합 무관하게 동일하게 `/approval`로 이동(중간 배너·`recipeBanner` state/JSX 제거). 승인 화면이 이미 Human-in-the-Loop 단계라 중복 마찰 제거
- `ApprovalPage.jsx`: 제목 옆에 `✅ 검증된 레시피 · 확인 실험` 배지 추가(`suggestion.recipe_found`) — 제거한 배너의 맥락 보존

### 2. 승인 화면 SHAP 그래프 라벨 (`ApprovalPage.jsx`)
- 왼쪽 Y축 라벨 잘림 해결: raw 키 대신 `FEATURE_LABELS` 적용(`shapData`에 `label` 필드 추가, `YAxis dataKey="label"`), `width` 90→120, 폰트 12
- 파생변수 라벨 한·영 혼용 정리 → **전부 영어 통일**: 에너지 밀도→`Energy Density`, 정규화 Power→`Normalized Power`, Thickness 비율→`Thickness Ratio` (원본 7개 + 파생 5개 전부 영어)
- 파생변수 개념 정리: `feature_engineering.py`의 energy_density/power_x_defocus/freq_x_power/thickness_ratio/normalized_power = 입력값으로 모델이 자동 계산하는 조합 변수

### 3. 결과 보고 화면 "AI 평가" 버튼 (`ResultPage.jsx`)
- 문구 `AI 평가로 채우기` → `AI 평가`, `btn-sm` → `btn-sm btn-primary`(배경색으로 구분)
- 버그 수정: 설명 영역이 `<label>`이라 라벨 빈 공간 클릭 시 첫 폼 요소(버튼)가 눌림 → 바깥 `<label>`을 `<div>`로 변경(버튼만 클릭에 반응)

### 4. 테스트 데이터 정리 — 판정/생성시각 필터 (`DataManagementSection.jsx`)
- 판정 종류·생성시각으로 목록을 좁혀 선택·삭제하도록 필터 추가(client-side, 백엔드 변경 없음)
- 초기엔 표 위 별도 필터 줄 → 요청에 따라 **테이블 헤더 제목 클릭형(엑셀식)** `FilterHeader` 컴포넌트로 변경(제목 클릭 시 옵션 팝오버, `position:fixed`로 스크롤 영역 클리핑 회피, 활성 시 제목 강조+선택값 표시)
- 헤더 체크박스는 필터에 보이는 항목 기준 전체선택, 하단에 `N건 표시 · 선택 M건`+필터 초기화

### 5. 결과 저장 전 "실측 결과 확인" 모달 + 사전 판정 미리보기 (`ResultPage.jsx`)
- "결과 저장" 클릭 시 바로 저장하지 않고 확인 모달 표시: 승인 파라미터·실측 Kerf/Depth·결과 설명을 보여주고 [수정]/[확인 후 저장]
- **사전 판정 미리보기**: 입력한 Depth 기준 OK/미가공/과가공을 pill로 표시(+OK 기준 안내)
  - 백엔드: `doe_routes.py`에 `GET /doe/criteria` 신설(`DEPTH_OK_MIN/MAX`를 `.env`에서 반환 — 하드코딩 금지, 관리자 기준변경 즉시 반영). execution-agent 재빌드
  - 프론트: 진입 시 기준 fetch 후 서버 `judge_quality`와 동일 로직으로 미리보기 계산. NG(Defect)는 Depth만으로 판단 불가하여 제외 명시
- 모달 승인 파라미터 표시 다듬기: 한 줄→4줄, `Speed: 1000 mm/s` 형태로 콜론 기준 정렬(라벨 우측·값 우측, 2열 grid), 단위 괄호 제거

### 6. Phase 5·6 작업 정리 + 고객사 미팅 협의/확인 문서
- `scripts/gen_phase56_doc.py`: 동일 내용을 Word(.docx)+HTML 동시 생성(내용 동기화). 출력 `docs/Phase5-6_고객사미팅_정리.docx`/`.html`
- 구성: 진행현황, Phase 5(설치 사전준비물/현장작업/완료기준), Phase 6(실사/개발/완료기준), **현장 현황 파악(As-Is) 9개 분야**(CO₂ 가공기·인터페이스·AI장비 실물·네트워크·학습데이터 취득·소재/판정·개발기간/운영·발전계획·일정), 핵심 결정사항 10개 표

### 7. 브라우저 E2E 검증
- 백엔드 운영 플로우 14/14 통과: 검증레시피 흐름(recipe_found=true) + 신규 탐색(Bayesian) 각각 suggest→approve→evaluate(AI평가)→result, 탐색공간 준수 확인
- 헤드리스 캡처: 홈(네비7·폼·버튼), 관리자 콘솔(10섹션·헬스체크 전부 ok) 정상 렌더
- SHAP 반환 12개 키 전부 `FEATURE_LABELS` 매핑 확인(raw 키 노출 없음)
- 테스트 데이터 정리 엔드포인트 동작(삭제 2건) 확인
- **사전 판정 미리보기**: 서버 `judge_quality`와 미리보기 로직 경계값 8/8 일치. 기준 변경 반영 자동검증 6/6(관리자 PATCH로 MAX 25→20 → `/doe/criteria` 20 반영 → 실행중 서버 실제판정도 Depth22를 미가공으로 → 25 원복). 검증 중 생성 데이터 전량 정리, 기준 0/25 원복

### 검증 방식 메모
- `docker exec`로 띄운 python은 별도 프로세스라 docker-compose 원본 env를 읽음 → 판정 검증은 **실행 중 uvicorn 프로세스**의 `/doe/result`로 해야 정확(첫 시도 1건 FAIL은 이 측정오류였음)

### 다음 단계
- 본 세션 변경사항 git commit 미완료(이전 세션 누적분 포함)
- Phase 4 마무리: 승인화면 수정입력 탐색공간 가드(선택), 메뉴-SYSTEM_GUIDE 동기화 점검, 완료 보고 후 Phase 5 사전 준비물 착수

## 전체 UI 산업용 톤 리디자인 + 자동 알림(사내 SMTP/Grafana) + 메일 서버 설정 메뉴 (2026-06-14)

### 1. 전체 UI 리디자인 — 차분한 산업용(refined-industrial) 톤 (`ui-redesign` 브랜치, 14커밋)
- 공개 `frontend-design` 스킬 원칙을 직접 적용(플러그인 미활성). 작업 전 안전망: 태그 `ui-redesign-base`(=리디자인 직전) + 별도 브랜치
- 일관 디자인 언어: 헤더 모노스페이스 워드마크+`LASER PROCESS CONSOLE` 라벨+상단 액센트 라인 / 섹션 헤더 액센트 좌측 바 / 수치 판독값·입력 모노스페이스+각진(4px) 모서리(계기판 느낌) / 활성 강조는 네비탭·관리자탭·채팅세션 모두 동일 액센트 틴트 `rgba(37,99,235,0.08)`
- 적용 화면: Layout, 실험조건, AI제안승인, 결과보고, 레시피조회, 실험이력, AI채팅, 관리자 셸+10섹션(시스템상태/서비스/LLM/재학습/판정기준/소재종류/사용자/알림/감사로그/데이터)
- 개선: 레시피 조회 판정을 텍스트→pill 의미색으로 통일. 시스템상태 학습지표 표 라벨 한 줄(`.kv-table--labels-nowrap` 모디파이어 추가). 감사로그 운영자·시각 컬럼 nowrap → 행 높이 59→38px
- 안전원칙: 로직·핸들러·상태 className 무변경(style 속성만 교체), 메뉴 라벨/라우트 무변경(SYSTEM_GUIDE 동기화 불필요), 외부 폰트 미사용(오프라인 설비 안전)
- 검증: 화면별 vite build + eslint(베이스 대조로 신규 에러 0 확인) + Playwright 스모크(쓰기/DB 영향 작업은 미실행). 검증 방법은 메모리 `ades-ui-smoke-test`에 기록(npx 캐시 playwright + Chrome 채널)

### 2. 자동 알림 연결 — 사내 메일(SMTP) + Grafana 알림판 (`feature/notifications` 브랜치)
- 배경: 고객사 **폐쇄망(외부 접속 불가)** → 외부 Slack/Gmail 대신 사내 SMTP + Grafana(사내 DB 직접 조회)
- DB: `notifications` 이벤트 로그 테이블 신설(메일·Grafana 공통 백본). schema.sql + 운영 DB 반영
- `notifier.py` 신설: 설정 로드 + `smtplib` 사내 SMTP 발송 + DB 기록. **예외격리**(발송 실패가 결과저장 트랜잭션을 깨지 않음)
- `/doe/result` OK/실패 분기에 자동 알림 연결(`BackgroundTasks` 비차단). `/notifications/test`를 실제 메일 발송으로 교체(기존 'SMTP 미구현' 제거)
- `.env(.example)` `SMTP_*` 추가 — 비우면 메일 건너뛰고 DB/Grafana만 동작
- Grafana `notifications_overview.json`: 기존 `PostgreSQL-ades` 데이터소스로 판정분포/최근실패/알림이력 3패널(폐쇄망 동작)
- 모델 성능 저하 알림은 이번 범위 제외(임계값 정의 필요 — OK/실패만 연결)

### 3. 관리자 콘솔 '메일 서버 설정'(SMTP) 메뉴 (`feature/smtp-settings` 브랜치)
- 동기: SMTP가 `.env`에만 있어 변경 시 컨테이너 재빌드 필요 → UI에서 설정해 **DB 저장·런타임 반영**
- `notification_settings`에 `smtp_host/port/user/password/from/use_tls` 컬럼 추가(운영 DB + schema.sql)
- `notifier._resolve_smtp()`: SMTP 접속값을 **DB 우선·.env 폴백**으로 해석 → 재빌드 없이 즉시 반영
- admin: 설정 GET/PATCH에 `smtp_*` 포함, **비밀번호 마스킹**(응답엔 `smtp_password_set`만, 빈 값=변경 안 함), INSERT 경로 동적화
- frontend: 관리자 콘솔에 `MailServerSection`(메일 서버 설정) 탭 신설(알림설정↔감사로그 사이). chat.py SYSTEM_GUIDE 관리자 안내 보강
- 검증: GET/PATCH/마스킹 동작, **DB 저장값으로 루프백 SMTP 실제 발송(sent)** 확인

### 4. Gmail SMTP 실발송 검증 (개발 PC 한정)
- 개발 PC(인터넷 가능)에서 실제 메일 검증. 컨테이너 → `smtp.gmail.com:587` egress 확인
- 설정값: host `smtp.gmail.com` / port 587 / user·from = Gmail 주소 / 비번 = **Google 앱 비밀번호(16자리, 2단계 인증 필요)** / **STARTTLS ☑**
- 트러블슈팅: `SMTP AUTH extension not supported` = STARTTLS 꺼짐(`smtp_use_tls=f`) 상태에서 AUTH 시도 → STARTTLS 켜니 `Email: sent` 성공
- 주의: 폐쇄망에선 Gmail 불가 → 같은 화면에서 사내 SMTP로 교체(DB 저장이라 값만 변경)

### 5. main 병합
- 3개 브랜치를 `--no-ff`로 main 병합(파일 비중첩으로 충돌 0): `ui-redesign` → `feature/notifications` → `feature/smtp-settings`
- 병합 후 통합 빌드 통과. origin push는 미수행(요청 시), 병합 브랜치·`ui-redesign-base` 태그 보존

### 다음 단계
- 자동 알림 실제 동작(실험 OK/실패 → 메일+Grafana) 엔드투엔드 검증(알림 설정 토글 확인)
- 모델 성능 저하 알림(임계값 정의 후) 추가 검토
- 병합 브랜치 정리 및 origin push 여부 결정

---

## 개발플랜 백로그(RAG) 반영 + 관리자 게이트 테스트 바이패스 (2026-06-14)

### 1. AI 채팅 동작 방식 정리 → 개발플랜 백로그 신설
- 확인: AI 채팅은 LLM을 학습/파인튜닝하는 게 아니라, `system_manual.md`(없으면 `SYSTEM_GUIDE` 폴백) **전체 + 실시간 DB 요약**을 매 요청 프롬프트에 주입하는 **in-context 방식**(RAG 아님, `chat.py` 주석에 명시)
  - `SYSTEM_MANUAL`은 모듈 로드 시 1회만 읽음(`chat.py`) + execution-agent는 소스 볼륨 마운트 없음 → 매뉴얼 수정은 `docker compose build/up -d`로 재빌드해야 반영
- `docs/AI-ADES_개발플랜.md`: **"10. 향후 개선(백로그)"** 섹션 신설
  - AI 채팅 매뉴얼 **RAG 전환**(매뉴얼 비대화 시 지연·컨텍스트 한계 → Qdrant로 검색·주입), Grafana 패널 구성, 승인 수정입력 탐색공간 가드, 매뉴얼 즉시반영(볼륨 마운트+재읽기) 기록
  - (앞서) "Phase 4 실제 구현 현황(계획 대비 확장)"도 Phase 4 섹션에 추가 완료

### 2. 관리자 콘솔 비밀번호 게이트 — 테스트 바이패스 모드
- 요청: 테스트 단계에선 관리자 진입 시 **모달은 뜨되 비밀번호 검증 없이 [확인]만 누르면 입장**
- `frontend/src/config/adminAuth.js`: `ADMIN_AUTH_ENABLED=true`로 켜고 `ADMIN_AUTH_TEST_BYPASS=true` 신규 플래그 추가(운영 전환 시 false면 실제 비번 검증)
- `frontend/src/pages/AdminPage.jsx` `AdminGate`: 전체화면 카드 → **modal-overlay 팝업**으로 변경, "테스트 단계" 안내 배너, 바이패스 시 비번 검증 생략·세션 기억 안 함(진입 때마다 모달), [취소]는 홈 이동(useNavigate)
- HMR 즉시 반영(재빌드 불필요)

### 3. SHAP 전문가 해석 → 최적 조정 방향 제시 (방법 A+B)
- 배경: 기존 LLM 설명 프롬프트에 **SHAP 값이 아예 전달되지 않아** 일반적 추천 문구만 생성됨. SHAP를 해석해 "무엇을 어느 방향으로 바꿔야 OK에 드나"로 연결
- **방법 A — SHAP를 전문가 프롬프트에 주입** (`llm_explainer.py`)
  - `PROMPT_TEMPLATE`를 "가공 조건 최적화 전문가" 역할로 교체: SHAP 상위 5개 기여도(방향 포함)·OK 목표 밴드·변수 관계(에너지밀도=Power/Speed)·탐색공간 제약을 컨텍스트로 제공
  - `_format_shap()` + 한국어 라벨(`_FEATURE_LABELS_KO`) 추가. 출력은 ①SHAP 근거 해석 ②조정 제안(탐색공간 내) ③실측 확인 권고
  - `doe_routes.py`: 제안 시 LLM 컨텍스트에 `shap_values`·`thickness`·`depth_ok_min/max`(.env 기준) 추가
- **방법 B — 국소 What-if 민감도** (`doe_routes.py`)
  - `_param_neighbors()`: 탐색공간(`bayesian_opt._search_space()` 재사용, .env 기준) 안에서 각 파라미터 한 단계 위/아래 값 산출(Power는 범위 10%를 한 스텝)
  - `_local_sensitivity()`: 4개 조정 파라미터를 각각 한 단계씩 바꿔 `/predict` → `param 현재값→변경값: Depth ±Nμm`. **백그라운드 작업**에서 수행(응답 지연 없음)
  - 프롬프트에 `[국소 What-if]` 섹션 추가 + 조정 제안 시 그 Δdepth를 직접 근거로 삼도록 지시
- 검증: execution-agent 재빌드 후 `/doe/suggest`→설명 폴링. LLM이 SHAP 해석 + **실제 What-if 값**(예: "Speed 1000→500 시 Depth +4.2μm") 인용해 조정 방향 제시 확인. 승인 화면 "AI 설명" 패널에 그대로 반영(프론트 변경·DB 적재 없음)
- 후속: "정확히 몇 W에서 OK"까지는 Power 스윕 곡선(B 확장)으로 보완 가능 — 백로그
