# AI-ADES 운영 가이드

> CLAUDE.md 5장의 상세 버전. 서버 실행 명령, 환경변수 전체 목록, 컨테이너 재빌드 절차.

---

## 서버 실행 명령

```bash
# 전체 서비스 기동
docker-compose up -d

# agents 프로필 서비스(최초 빌드 필요)
docker-compose --profile agents build
docker-compose --profile agents up -d

# 개별 서비스 재시작 (코드만 바뀌고 의존성/Dockerfile 변경 없을 때)
docker-compose restart data-prep-agent
docker-compose restart modeling-agent
docker-compose restart execution-agent

# 코드 변경 후 이미지 재빌드가 필요한 경우 (volume mount 없음 - 소스가 이미지에 포함됨)
docker compose --profile agents build execution-agent
docker compose --profile agents up -d execution-agent

# 로그 확인
docker-compose logs -f modeling-agent

# 각 Agent 개발 모드 실행 (컨테이너 밖에서, 호스트에 의존성 설치 필요)
cd services/data-prep-agent  && uvicorn main:app --reload --port 8010
cd services/modeling-agent   && uvicorn main:app --reload --port 8011
cd services/execution-agent  && uvicorn main:app --reload --port 8012

# 프론트엔드 (Vite, HMR 적용됨)
cd frontend && npm run dev

# DB 스키마 초기화 / 갱신 (idempotent, IF NOT EXISTS)
Get-Content data/schema/schema.sql -Raw | docker exec -i pm-postgres psql -U ades -d ades_db

# MLflow UI 확인
http://localhost:5000

# Grafana 확인 (3002 아님! 3010)
http://localhost:3010
```

> ⚠ `execution-agent`, `data-prep-agent` 등은 docker-compose에 소스 볼륨 마운트가 없으므로,
> `main.py`/`admin.py` 등 백엔드 코드를 수정한 뒤에는 **반드시 이미지 재빌드 + 재기동**이 필요하다.
> (단순 `restart`만으로는 변경 사항이 반영되지 않음 — 이전 이미지로 재시작될 뿐)
> 프론트엔드(`frontend/`)는 `ades-frontend` 컨테이너에 `./frontend:/app`이 바인드 마운트되어 있어
> 코드 수정이 Vite HMR로 즉시 반영된다 (재빌드 불필요).

> ⚠ **`frontend/vite.config.js`를 수정한 경우, 수정 후 반드시 `docker compose restart frontend`를 실행할 것.**
> Windows + Docker Desktop 바인드 마운트 환경에서 vite가 설정 변경을 감지해 자체 재시작할 때
> 파일 감시기(FSWatcher)가 `/app`에 대해 `EIO`(입출력 오류)를 받아 Node 프로세스가 그대로 죽는 경우가 있다
> (`Error: EIO: i/o error, stat '/app'`, uncaught FSWatcher 'error' 이벤트).
> `restart: unless-stopped`로 결국 재기동되지만 Docker Desktop이 즉시 재시도하지 않으면
> frontend가 한동안(호스트 절전 시 수 시간) 다운된 상태로 남을 수 있다.
> → vite.config.js 변경 후에는 자동 재시작에 의존하지 말고 수동으로 `docker compose restart frontend` 실행.

---

## 환경변수 (.env 필수 항목)

```bash
# LLM
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b-instruct
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

Admin Console에서 LLM 설정(`LLM_PROVIDER`, `OLLAMA_MODEL`)과 판정 기준(`DEPTH_OK_MIN`, `DEPTH_OK_MAX`)은
`/admin/llm/switch`, `/admin/settings/quality-criteria`를 통해 런타임에 `.env`에 반영되고
재시작 없이 즉시 적용된다 (`env_utils.update_env`, `llm_explainer.reinitialize`).
