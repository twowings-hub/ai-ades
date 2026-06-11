-- ============================================================
-- AI-ADES 데이터베이스 스키마 (ades_db)
-- Phase 0: 환경 세팅
-- ============================================================

-- ------------------------------------------------------------
-- 1. experiments: 실험 조건 + 결과 (Excel POC 데이터 적재용)
--    Data 시트(Sample+Process) + Sheet1(Laser+Sensor+Result) 조인 결과
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS experiments (
    id              SERIAL PRIMARY KEY,

    -- 원본 식별자 (예: '300-2' 같은 비정형 No. 포함 가능 -> 문자열, 중복 적재 방지용 UNIQUE)
    exp_no          VARCHAR(20) NOT NULL UNIQUE,

    -- Sample 정보 (Data 시트)
    m1_glass        VARCHAR(50),            -- M1 (Glass) 종류
    m1_length_mm    NUMERIC(10, 3),         -- M1 length (4 / 10 / 20mm)
    m2_film         VARCHAR(50),            -- M2 (Film) 종류
    m2_length_mm    NUMERIC(10, 3),         -- M2 length (10 / 25 / 50mm)
    thickness_um    NUMERIC(10, 3),         -- Film 두께 (μm)

    -- Process 조건 (Data 시트)
    speed           NUMERIC(10, 3),         -- 가공 속도 (200 / 500 / 1000)
    defocus         NUMERIC(10, 3),         -- 디포커스 (0~4)

    -- Laser 조건 (Sheet1)
    frequency       NUMERIC(10, 3),         -- 주파수 (100 / 200 kHz)
    power           NUMERIC(10, 3),         -- 출력 (2.8~59.8 W)

    -- 센서 데이터 유무 (Sheet1, 'X' = 센서 없음 -> FALSE)
    sensor_data_ok  BOOLEAN DEFAULT TRUE,

    -- 결과 (Sheet1)
    kerf_um         NUMERIC(10, 3),         -- Kerf (μm)
    depth_um        NUMERIC(10, 3),         -- Depth (μm)
    quality         VARCHAR(10),            -- 미가공 / OK / 과가공 / NG

    -- 파생 컬럼: quality_score (OK=1, 미가공=0, 과가공=-1, NG=-2)
    quality_score   SMALLINT,

    -- 이상값 플래그: Thickness > 140um
    is_outlier      BOOLEAN DEFAULT FALSE,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_experiments_exp_no ON experiments (exp_no);
CREATE INDEX IF NOT EXISTS idx_experiments_quality ON experiments (quality);

-- ------------------------------------------------------------
-- 2. plasma_timeseries: Plasma 센서 시계열 데이터 (Phase 6)
--    실험(experiments) 1건에 대해 다수의 시계열 샘플이 매핑됨
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS plasma_timeseries (
    id              BIGSERIAL PRIMARY KEY,
    experiment_id   INTEGER NOT NULL REFERENCES experiments (id) ON DELETE CASCADE,

    -- 측정 시각 (가공 시작 시점 기준 상대 시간 또는 절대 시각)
    ts              TIMESTAMPTZ NOT NULL,
    elapsed_ms      NUMERIC(12, 3),         -- 가공 시작 후 경과 시간 (ms)

    -- Plasma 센서 채널 값
    channel         VARCHAR(50) NOT NULL,   -- 센서 채널명
    value           NUMERIC(14, 6) NOT NULL,-- 센서 측정값

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_plasma_ts_experiment ON plasma_timeseries (experiment_id);
CREATE INDEX IF NOT EXISTS idx_plasma_ts_ts ON plasma_timeseries (ts);

-- ------------------------------------------------------------
-- 3. recipes: Auto DOE 제안 / 운영자 승인 레시피
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recipes (
    id              SERIAL PRIMARY KEY,

    -- 소재 사양 (탐색 대상 소재 조합)
    m1_glass        VARCHAR(50),
    m1_length_mm    NUMERIC(10, 3),
    m2_film         VARCHAR(50),
    m2_length_mm    NUMERIC(10, 3),
    thickness_um    NUMERIC(10, 3),

    -- 레이저 조건 제안값 (탐색 공간 내 값만 허용)
    speed           NUMERIC(10, 3),         -- 200 / 500 / 1000
    defocus         NUMERIC(10, 3),         -- 0~4
    frequency       NUMERIC(10, 3),         -- 100 / 200
    power           NUMERIC(10, 3),         -- 2.8~59.8

    -- 모델 예측 결과
    pred_kerf_um    NUMERIC(10, 3),
    pred_depth_um   NUMERIC(10, 3),
    pred_quality    VARCHAR(10),            -- 미가공 / OK / 과가공 / NG
    confidence      NUMERIC(5, 4),          -- 0~1

    -- Auto DOE 시도 횟수 (OK 달성까지 걸린 회차)
    doe_attempts    INTEGER,

    -- 운영자 승인 워크플로우
    status          VARCHAR(20) NOT NULL DEFAULT 'proposed', -- proposed / approved / rejected
    approved_by     VARCHAR(50),
    approved_at     TIMESTAMPTZ,
    rejected_reason TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recipes_status ON recipes (status);

-- ------------------------------------------------------------
-- 4. model_metrics: 모델 학습 결과 이력 (Grafana 대시보드 조회용)
--    /model/train 호출 시마다 1행씩 적재 (MLflow run_id로 상세 추적)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_metrics (
    id              SERIAL PRIMARY KEY,

    kerf_r2         NUMERIC(6, 4),
    kerf_rmse       NUMERIC(10, 4),
    depth_r2        NUMERIC(6, 4),
    depth_rmse      NUMERIC(10, 4),
    quality_f1_macro NUMERIC(6, 4),
    quality_f1_ok   NUMERIC(6, 4),
    quality_accuracy NUMERIC(6, 4),

    mlflow_run_id_kerf    VARCHAR(64),
    mlflow_run_id_depth   VARCHAR(64),
    mlflow_run_id_quality VARCHAR(64),

    trained_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_model_metrics_trained_at ON model_metrics (trained_at);

-- ------------------------------------------------------------
-- 5. users: 관리자 콘솔 사용자 계정 (Phase 4)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    role            VARCHAR(20) DEFAULT 'operator',
    password_hash   VARCHAR(255),
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 6. notification_settings: 알림 설정 (Phase 4)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notification_settings (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(200),
    slack_webhook   VARCHAR(500),
    notify_on_ok    BOOLEAN DEFAULT TRUE,
    notify_on_failure           BOOLEAN DEFAULT TRUE,
    notify_on_model_degradation BOOLEAN DEFAULT TRUE,
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 7. audit_logs: 관리자 작업 감사 로그 (Phase 4)
--    action_type 값: 'llm_change' / 'approval' / 'rejection'
--                     'setting_change' / 'retrain' / 'service_restart'
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id              SERIAL PRIMARY KEY,
    action_type     VARCHAR(50),
    operator        VARCHAR(100),
    description     TEXT,
    old_value       JSONB,
    new_value       JSONB,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 8. approvals: Auto DOE 제안에 대한 운영자 승인/거부 이력 (Phase 3)
--    recipe_id: OK 판정 후 /doe/result 에서 recipes.id로 갱신 (Phase 3 추가)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS approvals (
    id            SERIAL PRIMARY KEY,
    suggestion_id VARCHAR(50) UNIQUE,
    status        VARCHAR(20),
    -- 'approved' / 'rejected' / 'modified'
    ai_params     JSONB,
    final_params  JSONB,
    operator_name VARCHAR(100),
    reason        TEXT,
    token         VARCHAR(100),
    expires_at    TIMESTAMP,
    recipe_id     INTEGER REFERENCES recipes (id),
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_approvals_suggestion_id ON approvals (suggestion_id);

-- ------------------------------------------------------------
-- 9. material_types: 소재 종류 관리 (Phase 4)
--    M1(Glass)/M2(Film) 소재 종류를 관리자 화면에서 등록/수정/비활성화하고
--    실험 조건 입력 화면(ExperimentPage)에서 선택할 수 있도록 한다
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS material_types (
    id              SERIAL PRIMARY KEY,
    category        VARCHAR(10) NOT NULL,   -- 'm1'(Glass) / 'm2'(Film)
    name            VARCHAR(50) NOT NULL,
    description     VARCHAR(200),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_material_types_category_name ON material_types (category, name);

-- 기존 POC 데이터(Glass/Film) 기본값 등록
INSERT INTO material_types (category, name, description) VALUES
    ('m1', 'Glass', 'POC 기본 M1 소재'),
    ('m2', 'Film', 'POC 기본 M2 소재')
ON CONFLICT (category, name) DO NOTHING;
