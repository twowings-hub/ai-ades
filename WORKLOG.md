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
