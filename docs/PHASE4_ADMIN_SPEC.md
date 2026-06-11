# Phase 4 Admin Console — 설계 및 구현 현황

> CLAUDE.md 5장에서 분리. Admin Console 전체 설계 + 구현 완료 항목 체크.
> 구현 위치: `services/execution-agent/admin.py`, `admin_data.py`, `material_types.py` (라우터로 main.py에 등록됨)
> 프론트: `frontend/src/pages/AdminPage.jsx` + `frontend/src/pages/admin/*Section.jsx`

---

## 1. 백엔드 엔드포인트

### [시스템 상태] ✅ 구현 완료
- `GET /admin/health` — data-prep:8010, modeling:8011, InfluxDB:8086, MLflow:5000, Grafana:3010, Kafka:9092 헬스체크 병렬 실행, 응답시간 측정
  → `{services: [{name, port, status, latency_ms}]}`
- `GET /admin/system-metrics` — psutil CPU/RAM/Disk + 현재 LLM 설정 + model_metrics 최신값
  → `{cpu, ram_used_gb, ram_total_gb, disk_used_gb, llm_provider, llm_model, model_metrics}`

### [LLM 관리] ✅ 구현 완료
- `GET /admin/llm/available-models` — ollama list 결과 + provider별 API 모델 고정 목록
  → `{ollama: [...], api: {claude: [...], openai: [...]}}`
  (2026-06-11: provider별로 분리, 이전엔 단일 배열이라 openai 선택 시 claude 모델까지 노출되는 버그 있었음 — 수정 완료)
- `POST /admin/llm/switch` — `.env` LLM_PROVIDER/OLLAMA_MODEL 수정, `llm_explainer` 런타임 재초기화, audit_logs 기록
- `POST /admin/llm/test` — 테스트 프롬프트 전송, `{success, response, latency_ms}`

### [모델 재학습] ✅ 구현 완료
- `POST /admin/model/retrain` (202) — modeling-agent `/model/train` 비동기 호출 + audit_logs
- `GET /admin/model/retrain-status` — `{status: "running"/"idle", progress, started_at}`

### [설정 관리] ✅ 구현 완료
- `PATCH /admin/settings/quality-criteria` — `DEPTH_OK_MIN`/`DEPTH_OK_MAX` 수정, 전 Agent 즉시 반영, audit_logs에 "이전값 → 새값" 기록
- `PATCH /admin/settings/search-space` — 탐색 공간 갱신 + Bayesian Opt 재초기화

### [사용자 관리] ✅ 구현 완료
- `GET/POST/PATCH /admin/users`

### [알림 설정] ✅ 구현 완료
- `GET/PATCH /admin/notifications/settings`, `POST /admin/notifications/test`

### [감사 로그] ✅ 구현 완료
- `GET /admin/audit-logs?page=&limit=` — action_type/operator/date_range 필터, 최신순

### [서비스 관리] ✅ 구현 완료
- `POST /admin/services/{service_name}/restart` — `docker-compose restart`, execution-agent 자기 자신 재시작은 차단

### [데이터 관리] ✅ 구현 완료
- `GET /admin/data/stats`, `POST /admin/data/backup`, `GET /admin/data/export`

### [소재 종류 관리] ✅ 구현 완료 (설계 당시 미포함, 추가 구현됨)
- `GET/POST/PATCH/DELETE /admin/material-types` — M1(Glass)/M2(Film) 소재 종류 CRUD
- `GET /material-types` (공개) — 실험 조건 입력 화면용 활성 목록

---

## 2. DB 테이블 (schema.sql)

- `users`, `notification_settings`, `audit_logs` — ✅ 적용됨
- `material_types` — ✅ 추가 적용됨 (설계 당시 미포함)

---

## 3. React 관리자 화면 (`/admin`)

사이드바 섹션 (`AdminPage.jsx`):

| # | 섹션 | 컴포넌트 | 상태 |
|---|---|---|---|
| 1 | 시스템 상태 | SystemStatusSection | ✅ |
| 2 | 서비스 관리 | ServiceManagementSection | ✅ |
| 3 | LLM 모델 선택 | LlmSection | ✅ |
| 4 | 모델 재학습 | RetrainSection | ✅ |
| 5 | 판정 기준 설정 | CriteriaSection | ✅ |
| 6 | 소재 종류 관리 | MaterialTypesSection | ✅ (추가 구현) |
| 7 | 사용자 관리 | UsersSection | ✅ |
| 8 | 알림 설정 | NotificationsSection | ✅ |
| 9 | 감사 로그 | AuditLogsSection | ✅ |
| 10 | 데이터 관리 | DataManagementSection | ✅ |

---

## 4. Phase 4 완료 기준 — 잔여 작업

1. ~~LLM 전환 엔드포인트~~ ✅ 확인됨
2. ~~판정 기준 변경 → 즉시 반영~~ ✅ 확인됨
3. React `/admin` 화면 — 섹션별 구현 완료, **E2E 통합 테스트(브라우저 실동작 확인) 잔여**
4. ~~감사 로그~~ ✅ 확인됨

### 다음 세션 작업 제안
- 브라우저에서 `/admin` 9~10개 섹션 전체를 순회하며 실동작 확인 (특히 LLM 전환/연결테스트, 모델 재학습 트리거, 백업/내보내기)
- ExperimentPage → ApprovalPage → ResultPage 전체 플로우 E2E 테스트 (신규 소재 종류 + 외삽 경고 케이스 포함)
- `data/test/AI-ADES_test_upload_sample_01~10.xlsx` 업로드 테스트로 `/data/upload` 동작 확인
